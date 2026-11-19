"""Display existing single-term LS significance without changing adoption."""
import numpy as np

from .. import execution
from . import settings as S


def validate_levels(levels):
    if any(isinstance(x, bool) or not np.isfinite(x) or not 0 < x < 1 for x in levels):
        raise ValueError('plot_fap_levels must contain probabilities strictly between 0 and 1')


def draw_fap(ax, result, row):
    if not S.PLOT_FAP:
        return
    validate_levels(S.PLOT_FAP_LEVELS)
    try:
        model = result['object']
        minimum_period = float(row.get('search_min_period_days', S.MIN_PERIOD_DAYS))
        # Match the existing raw FAP convention exactly: the same model, method
        # and maximum_frequency; Astropy defaults for other FAP arguments.
        levels = model.false_alarm_level(S.PLOT_FAP_LEVELS, method=S.LS_FAP_METHOD,
                                        maximum_frequency=1.0 / minimum_period)
        for probability, power in zip(S.PLOT_FAP_LEVELS, np.atleast_1d(levels), strict=True):
            if not np.isfinite(power):
                raise ValueError('non-finite analytical FAP threshold')
            ax.axhline(float(power), color='0.4', linestyle='--', linewidth=1,
                       label=f'{100 * probability:g}% FAP threshold')
        value = float(row.get('raw_ls_fap', result.get('raw_best_fap', np.nan)))
        label = f'Raw LS peak FAP={value:.2g}' if np.isfinite(value) else 'Raw LS peak FAP unavailable'
        ax.text(0.01, 0.98, label, transform=ax.transAxes, va='top', fontsize=8,
                bbox={'facecolor': 'white', 'alpha': 0.8, 'edgecolor': 'none'})
    except Exception as error:
        execution.report_exception(error, __name__)
        ax.text(0.01, 0.98, 'Analytical FAP level unavailable', transform=ax.transAxes,
                va='top', fontsize=8)
