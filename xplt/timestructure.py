#!/usr/bin/env python3
# -*- coding: utf-8 -*-

""" Methods for plotting particle arrival times

"""

__author__ = "Philipp Niedermayer"
__contact__ = "eltos@outlook.de"
__date__ = "2022-11-24"

import types

import matplotlib as mpl
import numpy as np
import pint

from .util import defaults
from .base import XManifoldPlot
from .particles import ParticlePlotMixin, ParticlesPlot
from .units import Prop


def binned_timeseries(times, n, what=None, range=None):
    """Get binned timeseries with equally spaced time bins

    From the particle arrival times (non-equally distributed timestamps), a timeseries with equally
    spaced time bins is derived. The time bin size is determined based on the number of bins.
    The parameter `what` determines what is returned for the timeseries. By default (what=None), the
    number of particles arriving within each time bin is returned. Alternatively, a particle property
    can be passed as array, in which case that property is averaged over all particles arriving within
    the respective bin (or 0 if no particles arrive within a time bin).

    Args:
        times: Array of particle arrival times.
        n: Number of bins.
        what: Array of associated data or None. Must have same shape as times. See above.
        range: Tuple of (min, max) time values to consider. If None, the range is determined from the data.

    Returns:
        The timeseries as tuple (t_min, dt, values) where
        t_min is the start time of the timeseries data,
        dt is the time bin width and
        values are the values of the timeseries as array of length n.
    """

    # Note: The code below was optimized to run much faster than an ordinary
    # np.histogram, which quickly slows down for large datasets.
    # If you intend to change something here, make sure to benchmark it!

    t_min = np.min(times) if range is None or range[0] is None else range[0]
    t_max = np.max(times) if range is None or range[1] is None else range[1]
    dt = (t_max - t_min) / n
    # count timestamps in bins
    bins = ((times - t_min) / dt).astype(int)
    # bins are i*dt <= t < (i+1)*dt where i = 0 .. n-1
    mask = (bins >= 0) & (bins < n)  # igore times outside range
    bins = bins[mask]
    # count particles per time bin
    counts = np.bincount(bins, minlength=n)[:n]

    if what is None:
        # Return particle counts
        return t_min, dt, counts

    else:
        # Return 'what' averaged
        v = np.zeros(n)
        # sum up 'what' for all the particles in each bin
        np.add.at(v, bins, what[mask])
        # divide by particle count to get mean (default to 0)
        v[counts > 0] /= counts[counts > 0]
        return t_min, dt, v


class TimePlot(ParticlesPlot):
    def __init__(self, particles=None, kind="x+y", **kwargs):
        """
        A thin wrapper around the ParticlesPlot plotting data as function of time.
        For more information refer to the documentation of the :class:`~xplt.particles.ParticlesPlot` class.

        The plot is based on the particle arrival time, which is:
            - For circular lines: at_turn / frev - zeta / beta / c0
            - For linear lines: zeta / beta / c0

        Args:
            particles: Particles data to plot.
            kind: Defines the properties to plot.
                    This can be a nested list or a separated string or a mixture of lists and strings where
                    the first list level (or separator ``,``) determines the subplots,
                    the second list level (or separator ``-``) determines any twinx-axes,
                    and the third list level (or separator ``+``) determines plots on the same axis.
                    In addition, abbreviations for x-y-parameter pairs are supported (e.g. 'bet' for 'betx+bety').
            kwargs: See :class:`~xplt.particles.ParticlesPlot` for more options.

        """
        super().__init__(particles, kind, as_function_of="t", **kwargs)


class TimeBinPlot(XManifoldPlot, ParticlePlotMixin):
    def __init__(
        self,
        particles=None,
        kind="count",
        *,
        bin_time=None,
        bin_count=None,
        exact_bin_time=True,
        relative=False,
        mask=None,
        plot_kwargs=None,
        twiss=None,
        beta=None,
        frev=None,
        circumference=None,
        wrap_zeta=False,
        **xplot_kwargs,
    ):
        """
        A binned histogram plot of particles as function of times.

        The plot is based on the particle arrival time, which is:
            - For circular lines: at_turn / frev - zeta / beta / c0
            - For linear lines: zeta / beta / c0

        The main purpose is to plot particle counts, but kind also accepts particle properties
        in which case the property is averaged over all particles falling into the bin.

        Useful to plot time structures of particles loss, such as spill structures.

        Args:
            particles: Particles data to plot.
            kind (str, optional): What to plot as function of time. Can be 'count' (default),
                'rate', 'cumulative', or a particle property to average.
            bin_time: Time bin width if bin_count is None.
            bin_count: Number of bins if bin_time is None.
            exact_bin_time (bool): What to do if bin_time is given but length of data is not an exact multiple of it.
                If True, overhanging data is removed such that the data length is a multiple of bin_time.
                If False, bin_time is adjusted instead.
            relative: If True, plot relative numbers normalized to total count.
                If what is a particle property, this has no effect.
            mask: An index mask to select particles to plot. If None, all particles are plotted.
            plot_kwargs: Keyword arguments passed to the plot function.
            twiss (dict, optional): Twiss parameters (alfx, alfy, betx and bety) to use for conversion to normalized phase space coordinates.
            beta (float, optional): Relativistic beta of particles. Defaults to particles.beta0.
            frev (float, optional): Revolution frequency of circular line for calculation of particle time.
            circumference (float, optional): Path length of circular line if frev is not given.
            wrap_zeta: If set, wrap the zeta-coordinate plotted at the machine circumference. Either pass the circumference directly or set this to True to use the circumference from twiss.
            xplot_kwargs: See :class:`xplt.XPlot` for additional arguments

        """
        xplot_kwargs = self._init_particle_mixin(
            twiss=twiss,
            beta=beta,
            frev=frev,
            circumference=circumference,
            wrap_zeta=wrap_zeta,
            xplot_kwargs=xplot_kwargs,
        )
        xplot_kwargs["data_units"] = defaults(
            xplot_kwargs.get("data_units"),
            count=Prop("$N$", unit="1", description="Particles per bin"),
            cumulative=Prop("$N$", unit="1", description="Particles (cumulative)"),
            rate=Prop("$\\dot{N}$", unit="1/s", description="Particle rate"),
        )
        super().__init__(
            on_x="t",
            on_y=kind,
            **xplot_kwargs,
        )

        if bin_time is None and bin_count is None:
            bin_count = 100
        self.bin_time = bin_time
        self.bin_count = bin_count
        self.exact_bin_time = exact_bin_time
        self.relative = relative

        # Format plot axes
        self.axis(-1).set(xlabel=self.label_for("t"), ylim=(0, None))
        if self.relative:
            for a in self.axflat:
                a.yaxis.set_major_formatter(mpl.ticker.PercentFormatter(1))

        # Create plot elements
        def create_artists(i, j, k, ax, p):
            kwargs = defaults(plot_kwargs, lw=1, label=self._legend_label_for(p))
            if p in ("count", "rate", "cumulative"):
                kwargs = defaults(kwargs, drawstyle="steps-pre")
            return ax.plot([], [], **kwargs)[0]

        self._init_artists(self.on_y, create_artists)

        # set data
        if particles is not None:
            self.update(particles, mask=mask, autoscale=True)

    def _get_property(self, p):
        prop = super()._get_property(p)
        if p not in ("count", "rate", "cumulative", "t"):
            # it is averaged
            prop = Prop(f"\\langle {prop.symbol} \\rangle", prop.unit, prop.description)
        return prop

    def update(self, particles, mask=None, autoscale=False):
        """Update plot with new data

        Args:
            particles: Particles data to plot.
            mask: An index mask to select particles to plot. If None, all particles are plotted.
            autoscale: Whether or not to perform autoscaling on all axes.

        Returns:
            list: Changed artists
        """

        # extract times
        times = self._get_masked(particles, "t", mask)

        # re-sample times into equally binned time series
        if self.bin_count:
            n = self.bin_count
            t_range = None
        elif self.exact_bin_time:
            n = int((np.max(times) - np.min(times)) / self.bin_time)
            t_range = np.min(times) + np.array([0, n * self.bin_time])
        else:
            n = int(round((np.max(times) - np.min(times)) / self.bin_time))
            t_range = None

        # update plots
        changed = []
        for i, ppp in enumerate(self.on_y):
            for j, pp in enumerate(ppp):
                count_based = False
                for k, p in enumerate(pp):
                    count_based = p in ("count", "rate", "cumulative")
                    if count_based:
                        property = None
                    else:
                        property = self._get_masked(particles, p, mask)

                    t_min, dt, timeseries = binned_timeseries(times, n, property, t_range)
                    timeseries = timeseries.astype(np.float64)
                    edges = np.linspace(t_min, t_min + dt * n, n + 1)

                    self.annotate(
                        f'$t_\\mathrm{{bin}} = {pint.Quantity(dt, "s").to_compact():~.4L}$'
                    )

                    if self.relative:
                        if not count_based:
                            raise ValueError(
                                "Relative plots are only supported for kind 'count', 'rate' or 'cumulative'."
                            )
                        timeseries /= len(times)

                    if p == "rate":
                        timeseries /= dt

                    # target units
                    edges *= self.factor_for("t")
                    if not count_based:
                        timeseries *= self.factor_for(p)

                    # update plot
                    if p == "cumulative":
                        # steps open after last bin
                        timeseries = np.concatenate(([0], np.cumsum(timeseries)))
                    elif count_based:
                        # steps go back to zero after last bin
                        edges = np.append(edges, edges[-1])
                        timeseries = np.concatenate(([0], timeseries, [0]))
                    else:
                        edges = (edges[1:] + edges[:-1]) / 2
                    self.artists[i][j][k].set_data((edges, timeseries))
                    changed.append(self.artists[i][j][k])

                if autoscale:
                    a = self.axis(i, j)
                    a.relim()
                    a.autoscale()
                    if count_based:
                        a.set(ylim=(0, None))

        return changed


class TimeFFTPlot(XManifoldPlot, ParticlePlotMixin):
    def __init__(
        self,
        particles=None,
        kind="count",
        *,
        fmax=None,
        relative=False,
        log=None,
        scaling=None,
        mask=None,
        plot_kwargs=None,
        twiss=None,
        beta=None,
        frev=None,
        circumference=None,
        wrap_zeta=False,
        **xplot_kwargs,
    ):
        """
        A frequency plot based on particle arrival times.

        The particle arrival time is:
            - For circular lines: at_turn / frev - zeta / beta / c0
            - For linear lines: zeta / beta / c0

        From the particle arrival times (non-equally distributed timestamps), a timeseries with equally
        spaced time bins is derived. The time bin size is determined based on fmax and performance considerations.
        By default, the binned property is the number of particles arriving within the bin time (what='count').
        Alternatively, a particle property may be specified (e.g. what='x'), in which case that property is
        averaged over all particles arriving in the respective bin. The FFT is then computed over the timeseries.

        Useful to plot time structures of particles loss, such as spill structures.

        Args:
            particles: Particles data to plot.
            kind (str, optional): What to make the FFT over. Can be 'count' (default), or a particle property (in which case averaging applies).
            fmax (float): Maximum frequency (in Hz) to plot.
            relative (bool): If True, plot relative frequencies (f/frev) instead of absolute frequencies (f).
            log (bool, optional): If True, plot on a log scale.
            scaling: Scaling of the FFT. Can be 'amplitude' or 'pds'.
            mask: An index mask to select particles to plot. If None, all particles are plotted.
            plot_kwargs: Keyword arguments passed to the plot function.
            twiss (dict, optional): Twiss parameters (alfx, alfy, betx and bety) to use for conversion to normalized phase space coordinates.
            beta (float, optional): Relativistic beta of particles. Defaults to particles.beta0.
            frev (float, optional): Revolution frequency of circular line for calculation of particle time.
            circumference (float, optional): Path length of circular line if frev is not given.
            wrap_zeta: If set, wrap the zeta-coordinate plotted at the machine circumference. Either pass the circumference directly or set this to True to use the circumference from twiss.
            xplot_kwargs: See :class:`xplt.XPlot` for additional arguments
        """
        xplot_kwargs = self._init_particle_mixin(
            twiss=twiss,
            beta=beta,
            frev=frev,
            circumference=circumference,
            wrap_zeta=wrap_zeta,
            xplot_kwargs=xplot_kwargs,
        )
        xplot_kwargs["data_units"] = defaults(
            xplot_kwargs.get("data_units"),
            count=Prop("N", unit="1", description="Particles per bin"),
        )
        super().__init__(
            on_x="t",
            on_y=kind,
            **xplot_kwargs,
        )

        if scaling is None:
            scaling = "pds" if kind == "count" else "amplitude"

        self._fmax = fmax
        self.relative = relative
        self.scaling = scaling
        if log is None:
            log = not relative

        # Format plot axes
        self.axis(-1).set(
            xlabel="$f/f_{rev}$" if self.relative else self.label_for("f"),
        )
        for a in self.axflat:
            a.set(ylim=(0, None))
            if log:
                a.set(
                    xscale="log",
                    yscale="log",
                )

        # Create plot elements
        def create_artists(i, j, k, ax, p):
            kwargs = defaults(plot_kwargs, lw=1, label=self._legend_label_for(p))
            return ax.plot([], [], **kwargs)[0]

        self._init_artists(self.on_y, create_artists)

        # set data
        if particles is not None:
            self.update(particles, mask=mask, autoscale=True)

    def fmax(self, particles):
        if self._fmax is not None:
            return self._fmax
        if self.relative:
            return self.frev(particles)
        raise ValueError("fmax must be specified.")

    def update(self, particles, mask=None, autoscale=False):
        """Update plot with new data

        Args:
            particles: Particles data to plot.
            mask: An index mask to select particles to plot. If None, all particles are plotted.
            autoscale: Whether or not to perform autoscaling on all axes.

        Returns:
            list: Changed artists
        """

        # extract times and associated property
        times = self._get_masked(particles, "t", mask)

        # re-sample times into equally binned time series
        fmax = self.fmax(particles)
        n = int(np.ceil((np.max(times) - np.min(times)) * fmax * 2))
        # to improve FFT performance, round up to next power of 2
        self.nbins = n = 1 << (n - 1).bit_length()

        # update plots
        changed = []
        for i, ppp in enumerate(self.on_y):
            for j, pp in enumerate(ppp):
                for k, p in enumerate(pp):
                    count_based = p == "count"
                    if count_based:
                        property = None
                    else:
                        property = self._get_masked(particles, p, mask)

                    # compute binned timeseries
                    t_min, dt, timeseries = binned_timeseries(times, n, property)

                    # calculate fft without DC component
                    freq = np.fft.rfftfreq(n, d=dt)[1:]
                    if self.relative:
                        freq /= self.frev(particles)
                    else:
                        freq *= self.factor_for("f")
                    mag = np.abs(np.fft.rfft(timeseries))[1:]
                    if self.scaling.lower() == "amplitude":
                        # amplitude in units of p
                        mag *= 2 / len(timeseries) * self.factor_for(p)
                    elif self.scaling.lower() == "pds":
                        # power density spectrum in a.u.
                        mag = mag**2

                    # update plot
                    self.artists[i][j][k].set_data(freq, mag)
                    changed.append(self.artists[i][j][k])

                if autoscale:
                    a = self.axis(i, j)
                    a.relim()
                    a.autoscale()
                    log = a.get_xscale() == "log"
                    xlim = np.array((10.0, fmax) if log else (0.0, fmax))
                    if self.relative:
                        xlim /= self.frev(particles)
                    else:
                        xlim *= self.factor_for("f")
                    a.set_xlim(xlim)
                    if a.get_yscale() != "log":
                        a.set_ylim(0, None)

        self.annotate(f"$t_\\mathrm{{bin}} = {pint.Quantity(dt, 's').to_compact():~.4L}$")

        return changed

    def _get_property(self, p):
        prop = super()._get_property(p)
        if p not in "f":
            # it is the FFT of it
            sym = prop.symbol.strip("$")
            if self.scaling.lower() == "amplitude":
                prop = Prop(f"$\\hat{{{sym}}}$", prop.unit, prop.description)
            elif self.scaling.lower() == "pds":
                prop = Prop(
                    f"$|\\mathrm{{FFT({sym})}}|^2$", "a.u.", prop.description
                )  # a.u. = arbitrary unit
            else:
                prop = Prop(
                    f"$|\\mathrm{{FFT({sym})}}|$", "a.u.", prop.description
                )  # a.u. = arbitrary unit
        return prop

    def plot_harmonics(self, f, df=0, *, n=20, **plot_kwargs):
        """Add vertical lines or spans indicating the location of values or spans and their harmonics

        Args:
            f (float or list of float): Fundamental frequency or list of frequencies in Hz.
            df (float or list of float, optional): Bandwidth or list of bandwidths centered around frequencies(s) in Hz.
            n (int): Number of harmonics to plot.
            plot_kwargs: Keyword arguments to be passed to plotting method
        """
        for a in self.axflat:
            super().plot_harmonics(
                a, self.factor_for("f") * f, self.factor_for("f") * df, n=n, **plot_kwargs
            )


class TimeIntervalPlot(XManifoldPlot, ParticlePlotMixin):
    def __init__(
        self,
        particles=None,
        *,
        tmax=None,
        bin_time=None,
        bin_count=None,
        exact_bin_time=True,
        log=True,
        mask=None,
        plot_kwargs=None,
        beta=None,
        frev=None,
        circumference=None,
        **xplot_kwargs,
    ):
        """
        A histogram plot of particle arrival intervals (i.e. delay between consecutive particles).

        The plot is based on the particle arrival time, which is:
            - For circular lines: at_turn / frev - zeta / beta / c0
            - For linear lines: zeta / beta / c0

        Useful to plot time structures of particles loss, such as spill structures.

        Args:
            particles: Particles data to plot.
            tmax: Maximum interval (in s) to plot.
            bin_time: Time bin width if bin_count is None.
            bin_count: Number of bins if bin_time is None.
            exact_bin_time (bool): What to do if bin_time is given but tmax is not an exact multiple of it.
                If True, tmax is adjusted to be a multiple of bin_time.
                If False, bin_time is adjusted instead.
            log: If True, plot on a log scale.
            mask: An index mask to select particles to plot. If None, all particles are plotted.
            plot_kwargs: Keyword arguments passed to the plot function.
            beta (float, optional): Relativistic beta of particles. Defaults to particles.beta0.
            frev (float, optional): Revolution frequency of circular line for calculation of particle time.
            circumference (float, optional): Path length of circular line if frev is not given.
            xplot_kwargs: See :class:`xplt.XPlot` for additional arguments

        """
        if tmax is None:
            raise ValueError("tmax must be specified.")

        if bin_time is not None:
            if exact_bin_time:
                tmax = bin_time * round(tmax / bin_time)
            else:
                bin_time = tmax / round(tmax / bin_time)

        xplot_kwargs = self._init_particle_mixin(
            beta=beta,
            frev=frev,
            circumference=circumference,
            xplot_kwargs=xplot_kwargs,
        )
        super().__init__(
            on_x="t",
            on_y="dt",
            **xplot_kwargs,
        )

        if bin_time is None and bin_count is None:
            bin_count = 100
        self._bin_time = bin_time
        self._bin_count = bin_count
        self.tmax = tmax

        # Format plot axes
        ax = self.axis(-1)
        ax.set(
            xlabel="Delay between consecutive particles " + self.label_for("t"),
            xlim=(self.bin_time if log else 0, self.tmax * self.factor_for("t")),
            ylabel=f"Occurrences",
        )
        if log:
            ax.set(xscale="log", yscale="log")
        else:
            ax.set(ylim=(0, None))

        # Create plot elements
        kwargs = defaults(plot_kwargs, lw=1)
        (self.artist,) = self.ax.step([], [], **kwargs)

        # set data
        if particles is not None:
            self.update(particles, mask=mask, autoscale=True)

    @property
    def bin_time(self):
        return self._bin_time or self.tmax / self._bin_count

    @property
    def bin_count(self):
        return int(np.ceil(self.tmax / self.bin_time))

    def update(self, particles, mask=None, autoscale=False):
        """Update plot with new data

        Args:
            particles: Particles data to plot.
            mask: An index mask to select particles to plot. If None, all particles are plotted.
            autoscale: Whether or not to perform autoscaling on all axes.
        """

        # extract times
        times = self._get_masked(particles, "t", mask)
        delay = self.factor_for("t") * np.diff(sorted(times))

        # calculate and plot histogram
        counts, edges = np.histogram(
            delay, bins=self.bin_count, range=(0, self.bin_count * self.bin_time)
        )
        steps = (np.append(edges, edges[-1]), np.concatenate(([0], counts, [0])))
        self.artist.set_data(steps)

        self.annotate(
            f"$t_\\mathrm{{bin}} = {pint.Quantity(self.bin_time, 's').to_compact():~.4L}$"
        )

        if autoscale:
            ax = self.axis(-1)
            ax.relim()
            ax.autoscale()
            if not ax.get_yscale() == "log":
                ax.set(ylim=(0, None))

    def plot_harmonics(self, t, *, n=20, **plot_kwargs):
        """Add vertical lines or spans indicating the location of values or spans and their harmonics

        Args:
            t (float or list of float): Period in s.
            n (int): Number of harmonics to plot.
            plot_kwargs: Keyword arguments to be passed to plotting method
        """
        for a in self.axflat:
            super().plot_harmonics(a, self.factor_for("t") * t, n=n, **plot_kwargs)


class TimeVariationPlot(XManifoldPlot, ParticlePlotMixin):
    def __init__(
        self,
        particles=None,
        metric="cv",
        *,
        counting_dt=None,
        counting_bins=None,
        evaluate_dt=None,
        evaluate_bins=None,
        poisson=True,
        mask=None,
        plot_kwargs=None,
        beta=None,
        frev=None,
        circumference=None,
        **xplot_kwargs,
    ):
        """
        Plot for variability of particles arriving as function of arrival time

        The plot is based on the particle arrival time, which is:
            - For circular lines: at_turn / frev - zeta / beta / c0
            - For linear lines: zeta / beta / c0

        Useful to plot time structures of particles loss, such as spill structures.

        The following metrics are implemented:
            cv: Coefficient of variation
                cv = std(N)/mean(N)
            duty: Spill duty factor
                F = mean(N)**2 / mean(N**2)

        Args:
            particles: Particles data to plot.
            metric (str): Metric to plot. See above for list of implemented metrics.
            counting_dt: Time bin width for counting if counting_bins is None.
            counting_bins: Number of bins if counting_dt is None.
            evaluate_dt: Time bin width for metric evaluation if evaluate_bins is None.
            evaluate_bins: Number of bins if evaluate_dt is None.
            poisson (bool): If true, indicate poisson limit.
            mask: An index mask to select particles to plot. If None, all particles are plotted.
            plot_kwargs: Keyword arguments passed to the plot function.
            beta (float, optional): Relativistic beta of particles. Defaults to particles.beta0.
            frev (float, optional): Revolution frequency of circular line for calculation of particle time.
            circumference (float, optional): Path length of circular line if frev is not given.
            xplot_kwargs: See :class:`xplt.XPlot` for additional arguments
        """
        xplot_kwargs = self._init_particle_mixin(
            beta=beta,
            frev=frev,
            circumference=circumference,
            xplot_kwargs=xplot_kwargs,
        )
        xplot_kwargs["data_units"] = defaults(
            xplot_kwargs.get("data_units"),
            cv=Prop("$c_v=\\sigma/\\mu$", unit="1", description="Coefficient of variation"),
            duty=Prop(
                "$F=\\langle N \\rangle^2/\\langle N^2 \\rangle$",
                unit="1",
                description="Spill duty factor",
            ),
        )
        super().__init__(
            on_x="t",
            on_y=metric,
            **xplot_kwargs,
        )

        if counting_dt is None and counting_bins is None:
            counting_bins = 100 * 100
        if evaluate_dt is None and evaluate_bins is None:
            evaluate_bins = 100
        self.counting_dt = counting_dt
        self.counting_bins = counting_bins
        self.evaluate_dt = evaluate_dt
        self.evaluate_bins = evaluate_bins

        # Format plot axes
        self.axis(-1).set(xlabel=self.label_for("t"), ylim=(0, None))
        for i, ppp in enumerate(self.on_y):
            for j, pp in enumerate(ppp):
                a = self.axis(i, j)
                if np.all(np.array(pp) == "duty"):
                    a.yaxis.set_major_formatter(mpl.ticker.PercentFormatter(1))

        # Create plot elements
        def create_artists(i, j, k, ax, p):
            kwargs = defaults(plot_kwargs, lw=1, label=self._legend_label_for(p))
            step = ax.step([], [], **kwargs)[0]
            if poisson:
                kwargs.update(
                    color=step.get_color() or "gray",
                    alpha=0.5,
                    zorder=1.9,
                    lw=1,
                    ls=":",
                    label="Poisson limit",
                )
                pstep = ax.step([], [], **kwargs)[0]
            else:
                pstep = None
            return step, pstep

        self._init_artists(self.on_y, create_artists)

        # set data
        if particles is not None:
            self.update(particles, mask=mask, autoscale=True)

    def update(self, particles, mask=None, autoscale=False):
        """Update plot with new data

        Args:
            particles: Particles data to plot.
            mask: An index mask to select particles to plot. If None, all particles are plotted.
            autoscale: Whether or not to perform autoscaling on all axes.

        Returns:
            Changed artists
        """

        # extract times
        times = self._get_masked(particles, "t", mask)

        # re-sample times into equally binned time series
        ncbins = self.counting_bins or int(
            np.ceil((np.max(times) - np.min(times)) / self.counting_dt)
        )
        if self.evaluate_bins is not None:
            nebins = int(ncbins / self.evaluate_bins)
        else:
            nebins = int(ncbins * self.evaluate_dt / (np.max(times) - np.min(times)))

        # update plots
        changed = []
        for i, ppp in enumerate(self.on_y):
            for j, pp in enumerate(ppp):
                for k, p in enumerate(pp):
                    # bin into counting bins
                    t_min, dt, counts = binned_timeseries(times, ncbins)
                    edges = np.linspace(t_min, t_min + dt * ncbins, ncbins + 1)

                    # make 2D array by subdividing into evaluation bins
                    N = counts = counts[: int(len(counts) / nebins) * nebins].reshape(
                        (-1, nebins)
                    )
                    edges = edges[: int(len(edges) / nebins + 1) * nebins : nebins]

                    self.annotate(
                        f'$t_\\mathrm{{bin}} = {pint.Quantity(dt*nebins, "s").to_compact():~.4L}$\n'
                        f'$t_\\mathrm{{measure}} = {pint.Quantity(dt, "s").to_compact():~.4L}$'
                    )

                    # calculate metrics
                    if p == "cv":
                        F = np.std(N, axis=1) / np.mean(N, axis=1)
                        F_poisson = 1 / np.mean(N, axis=1) ** 0.5
                    elif p == "duty":
                        F = np.mean(N, axis=1) ** 2 / np.mean(N**2, axis=1)
                        F_poisson = 1 / (1 + 1 / np.mean(N, axis=1))
                    else:
                        raise ValueError(f"Unknown metric {p}")

                    # update plot
                    step, pstep = self.artists[i][j][k]
                    edges = self.factor_for("t") * np.append(edges, edges[-1])
                    steps = np.concatenate(([0], F, [0]))
                    step.set_data((edges, steps))
                    changed.append(step)
                    if pstep:
                        steps = np.concatenate(([0], F_poisson, [0]))
                        pstep.set_data((edges, steps))
                        changed.append(pstep)

                if autoscale:
                    a = self.axis(i, j)
                    a.relim()
                    a.autoscale()
                    a.set(ylim=(0, None))
        return changed


## Restrict star imports to local namespace
__all__ = [
    name
    for name, thing in globals().items()
    if not (name.startswith("_") or isinstance(thing, types.ModuleType))
]
