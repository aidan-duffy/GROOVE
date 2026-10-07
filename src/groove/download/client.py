from __future__ import annotations
import argparse
import hashlib
import os
import re
import time
from io import StringIO
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urljoin, urlparse
import pandas as pd
import requests
from pandas.errors import EmptyDataError
from . import settings as S
from . import run as _run
from . import storage as _storage
from . import targets as _targets




class AuthenticationError(RuntimeError):
    """The supplied token was rejected by ATLAS."""


class RetryableError(RuntimeError):
    """A temporary/API/network condition should be retried later."""


class PermanentJobError(RuntimeError):
    """A non-retryable target/job error."""


class AtlasClient:
    def __init__(self, token: str, args: argparse.Namespace) -> None:
        self.args = args
        self.session = requests.Session()
        self.session.headers.update(
            {"Authorization": f"Token {token}", "Accept": "application/json"}
        )

    @property
    def timeout(self) -> Tuple[int, int]:
        return S.CONNECT_TIMEOUT_SECONDS, S.READ_TIMEOUT_SECONDS

    def close(self) -> None:
        self.session.close()

    def validate_authentication(self) -> None:
        try:
            response = self.session.get(f"{S.BASEURL}/queue/", timeout=self.timeout)
        except requests.RequestException as exc:
            raise RetryableError(
                f"Could not perform initial ATLAS connectivity check: {exc}"
            ) from exc
        if response.status_code in (401, 403):
            raise AuthenticationError(
                f"ATLAS rejected token "
                f"(HTTP {response.status_code})."
            )
        # Some installations may not allow GET on this endpoint. Any non-auth
        # response is sufficient here; the first submit will provide full detail.

    def _message(self, response: requests.Response) -> str:
        try:
            body = response.json()
            if isinstance(body, dict):
                return str(body.get("detail") or body.get("error") or body)
            return str(body)
        except Exception:
            return response.text[:1000]

    def _retry_wait(self, message: str, attempt: int) -> float:
        seconds = re.search(r"available in\s+(\d+)\s+seconds?", message, re.I)
        minutes = re.search(r"available in\s+(\d+)\s+minutes?", message, re.I)
        if seconds:
            return float(seconds.group(1))
        if minutes:
            return float(minutes.group(1)) * 60.0
        return float(self.args.retry_delay) * max(1, attempt + 1)

    def submit_job(
        self,
        ra: float,
        dec: float,
        mjd_min: Optional[float],
        mjd_max: Optional[float],
        mode: str,
    ) -> Tuple[str, str]:
        payload: Dict[str, Any] = {
            "ra": float(ra),
            "dec": float(dec),
            "use_reduced": _storage.mode_to_use_reduced(mode),
            "send_email": "false",
        }
        # The server model has a recent-data default for a missing mjd_min.
        # Explicit blank values are therefore required for a true full-history
        # request; numeric baselines send the frozen MJD limits.
        if mjd_min is None and mjd_max is None:
            payload["mjd_min"] = ""
            payload["mjd_max"] = ""
        else:
            if mjd_min is not None:
                payload["mjd_min"] = float(mjd_min)
            if mjd_max is not None:
                payload["mjd_max"] = float(mjd_max)

        last_error = ""
        for attempt in range(int(self.args.max_retries) + 1):
            if S.STOP_EVENT.is_set():
                raise KeyboardInterrupt
            try:
                response = self.session.post(
                    f"{S.BASEURL}/queue/", data=payload, timeout=self.timeout
                )
            except requests.RequestException as exc:
                raise RetryableError("Submission outcome is unknown after a network error. Check your ATLAS queue before retrying.") from exc

            if response.status_code in (401, 403):
                raise AuthenticationError(
                    f"ATLAS rejected token "
                    f"(HTTP {response.status_code})."
                )
            if response.status_code in (200, 201, 202):
                try:
                    body = response.json()
                except ValueError as exc:
                    raise RetryableError(
                        "ATLAS accepted a job but returned non-JSON metadata."
                    ) from exc
                task_url = body.get("url") or body.get("task_url")
                if not task_url:
                    raise RetryableError(
                        f"ATLAS submission response had no task URL. Keys: {list(body)}"
                    )
                task_url = urljoin(f"{S.BASEURL}/", str(task_url))
                job_id = str(body.get("id") or extract_job_id(task_url))
                return task_url, job_id

            message = self._message(response)
            if 500 <= response.status_code < 600:
                raise RetryableError("Submission outcome is unknown after an ATLAS server error. Check your queue before retrying.")
            if response.status_code == 429:
                last_error = f"HTTP {response.status_code}: {message}"
                if attempt >= int(self.args.max_retries):
                    break
                wait = self._retry_wait(message, attempt)
                _run.print_safe(
                    f"[ATLAS] temporary submit error; retrying in "
                    f"{wait:.0f} s — {last_error}"
                )
                time.sleep(wait)
                continue

            raise PermanentJobError(
                f"ATLAS queue request failed (HTTP {response.status_code}): {message}"
            )

        raise RetryableError(
            f"Submission still failed after {self.args.max_retries} retries: {last_error}"
        )

    def poll_job(
        self,
        task_url: str,
        state_callback: Callable[[str, Dict[str, Any]], None],
    ) -> Dict[str, Any]:
        start = time.monotonic()
        consecutive_errors = 0
        previous_state = ""
        last_console = 0.0

        while not S.STOP_EVENT.is_set():
            if self.args.max_poll_hours > 0:
                elapsed_hours = (time.monotonic() - start) / 3600.0
                if elapsed_hours > float(self.args.max_poll_hours):
                    raise RetryableError(
                        f"Polling exceeded {self.args.max_poll_hours:g} hours; the "
                        "stored task URL will be resumed on restart."
                    )

            try:
                response = self.session.get(task_url, timeout=self.timeout)
            except requests.RequestException as exc:
                consecutive_errors += 1
                if consecutive_errors > int(self.args.max_retries):
                    raise RetryableError(
                        f"Polling network errors exceeded --max-retries: {exc}"
                    ) from exc
                time.sleep(float(self.args.retry_delay))
                continue

            if response.status_code in (401, 403):
                raise AuthenticationError(
                    f"ATLAS rejected token while polling "
                    f"(HTTP {response.status_code})."
                )
            if response.status_code == 429 or 500 <= response.status_code < 600:
                consecutive_errors += 1
                message = self._message(response)
                if consecutive_errors > int(self.args.max_retries):
                    raise RetryableError(
                        f"Polling failed repeatedly (HTTP {response.status_code}): {message}"
                    )
                S.STOP_EVENT.wait(self._retry_wait(message, consecutive_errors - 1))
                continue
            if response.status_code >= 400:
                raise PermanentJobError(
                    f"Task polling failed (HTTP {response.status_code}): "
                    f"{self._message(response)}"
                )

            consecutive_errors = 0
            try:
                task = response.json()
            except ValueError as exc:
                raise RetryableError("ATLAS task endpoint returned non-JSON data.") from exc

            error_text = _targets.clean_cell(
                task.get("error_msg") or task.get("error") or task.get("failure_reason")
            )
            task_status = _targets.clean_cell(task.get("status")).lower()
            if task_status in {"failed", "error", "cancelled"}:
                raise PermanentJobError(error_text or f"ATLAS task status was {task_status}.")

            if task.get("finishtimestamp") or task_status in {
                "finished", "complete", "completed", "done"
            }:
                state_callback("completed", task)
                return task

            if task.get("starttimestamp") or task_status in {"running", "started"}:
                state = "running"
            else:
                state = "submitted"

            now = time.monotonic()
            if state != previous_state:
                state_callback(state, task)
                previous_state = state
                last_console = now
            elif now - last_console >= max(30.0, float(self.args.poll_seconds) * 5.0):
                state_callback(state, task)
                last_console = now

            S.STOP_EVENT.wait(float(self.args.poll_seconds))

        raise KeyboardInterrupt

    def download_result(self, result_url: str) -> pd.DataFrame:
        result_url = urljoin(f"{S.BASEURL}/", result_url)
        last_error = ""
        for attempt in range(int(self.args.max_retries) + 1):
            if S.STOP_EVENT.is_set():
                raise KeyboardInterrupt
            try:
                response = self.session.get(result_url, timeout=self.timeout)
            except requests.RequestException as exc:
                last_error = f"network error while downloading: {exc}"
                if attempt >= int(self.args.max_retries):
                    break
                time.sleep(float(self.args.retry_delay) * max(1, attempt + 1))
                continue

            if response.status_code in (401, 403):
                raise AuthenticationError(
                    f"ATLAS rejected token while "
                    f"downloading (HTTP {response.status_code})."
                )
            if response.status_code == 429 or 500 <= response.status_code < 600:
                last_error = f"HTTP {response.status_code}: {self._message(response)}"
                if attempt >= int(self.args.max_retries):
                    break
                time.sleep(self._retry_wait(last_error, attempt))
                continue
            if response.status_code >= 400:
                raise PermanentJobError(
                    f"Result download failed (HTTP {response.status_code}): "
                    f"{self._message(response)}"
                )

            text = response.text.strip()
            if not text or re.search(r"\bno\s+data\b", text, re.I):
                return pd.DataFrame()
            try:
                df = pd.read_csv(StringIO(text), sep="," if "," in text.splitlines()[0] else r"\s+")
            except EmptyDataError:
                return pd.DataFrame()
            except Exception as first_error:
                try:
                    df = pd.read_csv(StringIO(text))
                except Exception as second_error:
                    raise PermanentJobError(
                        "Downloaded result could not be parsed as whitespace- or "
                        f"comma-separated data: {first_error}; {second_error}"
                    ) from second_error

            if not {"MJD", "###MJD"}.intersection(df.columns):
                raise PermanentJobError("ATLAS result has no MJD column; refusing to save malformed data.")
            df = df.rename(columns={"###MJD": "MJD"})
            return df

        raise RetryableError(
            f"Result download still failed after {self.args.max_retries} retries: "
            f"{last_error}"
        )


def extract_job_id(task_url: str) -> str:
    path = urlparse(task_url).path.rstrip("/")
    return path.split("/")[-1] if path else hashlib.sha1(task_url.encode()).hexdigest()[:12]


def extract_result_url(task: Dict[str, Any]) -> str:
    for key in ("result_url", "resulturl", "result", "download_url", "data_url"):
        value = task.get(key)
        if value:
            return urljoin(f"{S.BASEURL}/", str(value))
    return ""


def load_token() -> str:
    """Read the user's token without writing it to configs or progress files."""
    token = os.environ.get("ATLAS_TOKEN", "").strip()
    if not token or token == "your-token-here":
        raise EnvironmentError("Set ATLAS_TOKEN to your ATLAS forced-photometry token before downloading.")
    return token
