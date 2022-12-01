#!/usr/bin/env python3
# -*- coding: utf-8 -*-

""" Methods for plotting particle arrival times

"""

__author__ = "Philipp Niedermayer"
__contact__ = "eltos@outlook.de"
__date__ = "2022-11-24"


import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import os

import pint

from .base import Xplot, style, get

c0 = 299792458  # speed of light in m/s


class _TimestructurePlotMixin:
    def __init__(self, beta, frev=None, *args, **kwargs):
        """A mixing for plots which are based on the particle arrival time

        Args:
            beta: Relativistic beta of particles.
            frev: Revolution frequency of circular line. If None for linear lines.
        """
        if beta is None:
            raise ValueError("beta is a required parameter.")
        super().__init__(*args, **kwargs)
        self.beta = beta
        self.frev = frev

    def particle_arrival_times(self, particles, mask=None):
        """Get particle arrival times

        Args:
            particles: Particles data to plot.
            mask: An index mask to select particles to plot. If None, all particles are plotted.

        """
        turn = get(particles, "at_turn")
        zeta = get(particles, "zeta")
        if mask is not None:
            turn = turn[mask]
            zeta = zeta[mask]

        time = -zeta / self.beta / c0  # zeta>0 means early; zeta<0 means late
        if self.frev is not None:
            time = time + turn / self.frev
        elif np.any(turn > 0):
            raise ValueError("frev is required for non-circular lines where turn > 0.")

        return time

    @staticmethod
    def binned_timeseries(times, n, what=None):
        """Get binned timeseries with equally spaced time bins

        From the particle arrival times (non-equally distributed timestamps), a timeseries with equally
        spaced time bins is derived. The time bin size is determined based on the number of bins.
        The parameter `what` determines what is returned for the timeseries. By default (what=None), the
        number of particles arriving within each time bin is returned. Alternatively, a particle property
        can be passed as array, in which case that property is averaged over all particles arriving within
        the respective bin (or 0 if no particles arrive within a time bin).

        Args:
            times: Array of particle arrival times.
            what: Array of associated data or None. Must have same shape as times. See above.
            n: Number of bins.

        Returns:
            The timeseries as tuple (t_min, dt, values) where
            t_min is the start time of the timeseries data,
            dt is the time bin width and
            values are the values of the timeseries as array of length n.
        """

        # Note: The code below was optimized to run much faster than an ordinary
        # np.histogram, which quickly slows down for large datasets.
        # If you intend to change something here, make sure to benchmark it!

        t_min = np.min(times)
        dt = (np.max(times) - t_min) / n
        # count timestamps in bins
        bins = ((times - t_min) / dt).astype(int)
        # bins are i*dt <= t < (i+1)*dt where i = 0 .. n-1
        bins = np.clip(bins, None, n - 1)  # but for the last bin use t <= n*dt
        # count particles per time bin
        counts = np.bincount(bins)  # , minlength=n)[:n]

        if what is None:
            # Return particle counts
            return t_min, dt, counts

        else:
            # Return 'what' averaged
            v = np.zeros(n)
            # sum up 'what' for all the particles in each bin
            np.add.at(v, bins, what)
            # divide by particle count to get mean (default to 0)
            v[counts > 0] /= counts[counts > 0]
            return t_min, dt, v


class TimeHistPlot(_TimestructurePlotMixin, Xplot):
    def __init__(
        self,
        particles=None,
        *,
        beta=None,
        frev=None,
        bin_time=None,
        bin_count=None,
        plot="counts",
        ax=None,
        mask=None,
        relative=False,
        range=None,
        display_units=None,
        step_kwargs=None,
        grid=True,
        **subplots_kwargs,
    ):
        """
        A histogram plot of particle arrival times.

        The plot is based on the particle arrival time, which is:
            - For circular lines: at_turn / frev - zeta / beta / c0
            - For linear lines: zeta / beta / c0

        Useful to plot time structures of particles loss, such as spill structures.

        Args:
                particles: Particles data to plot.
                beta: Relativistic beta of particles.
                frev: Revolution frequency of circular line. If None for linear lines.
                bin_time: Time bin width if bin_count is None.
                bin_count: Number of bins if bin_time is None.
                plot: Plot type. Can be 'counts' (default), 'rate' or 'cumulative'.
                ax: An axes to plot onto. If None, a new figure is created.
                mask: An index mask to select particles to plot. If None, all particles are plotted.
                relative: If True, plot relative numbers normalized to total count.
                range: A tuple of (min, max) time values defining the histogram range.
                display_units: Dictionary with units for parameters.
                step_kwargs: Keyword arguments passed to matplotlib.pyplot.step() plot.
                grid (bool): En- or disable showing the grid
                subplots_kwargs: Keyword arguments passed to matplotlib.pyplot.subplots command when a new figure is created.

        """
        super().__init__(beta, frev, display_units=display_units)

        if bin_time is None and bin_count is None:
            bin_count = 100
        self.plot = plot
        self.bin_time = bin_time
        self.bin_count = bin_count
        self.relative = relative
        self.range = range

        # Create plot axes
        if ax is None:
            _, ax = plt.subplots(**subplots_kwargs)
        self.ax = ax
        self.fig = self.ax.figure

        # Create distribution plots
        kwargs = style(step_kwargs, lw=1)
        (self.artist_hist,) = self.ax.step([], [], **kwargs)
        self.ax.set(xlabel=self.label_for("t"), ylim=(0, None))
        self.ax.grid(grid)
        if self.relative:
            self.ax.yaxis.set_major_formatter(mpl.ticker.PercentFormatter(1))

        # set data
        if particles is not None:
            self.update(particles, mask=mask, autoscale=True)

    def update(self, particles, mask=None, autoscale=False):
        """Update plot with new data

        Args:
            particles: Particles data to plot.
            mask: An index mask to select particles to plot. If None, all particles are plotted.
            autoscale: Whether or not to perform autoscaling on all axes.
        """

        # extract times
        times = self.particle_arrival_times(particles, mask=mask)

        # histogram settings
        bin_time = self.bin_time or (np.max(times) - np.min(times)) / self.bin_count
        range = self.range or (np.min(times), np.max(times))
        nbins = int(np.ceil((range[1] - range[0]) / bin_time))
        range = (range[0], range[0] + nbins * bin_time)  # ensure exact bin width

        # calculate and plot histogram
        weights = np.ones_like(times)
        if self.plot == "rate":
            weights /= bin_time
        if self.relative:
            weights /= len(times)
        counts, edges = np.histogram(times, bins=nbins, weights=weights, range=range)
        edges *= self.factor_for("t")

        # update plot
        if self.plot == "cumulative":
            counts = np.cumsum(counts)
            steps = (edges, np.concatenate(([0], counts)))
        else:
            steps = (np.append(edges, edges[-1]), np.concatenate(([0], counts, [0])))
        self.artist_hist.set_data(steps)

        if autoscale:
            self.ax.relim()
            self.ax.autoscale()
            self.ax.set(ylim=(0, None))

        # label
        ylabel = "Particle" + (" fraction" if self.relative else "s")
        if self.plot == "rate":
            ylabel += " / s"
        elif self.plot != "cumulative":
            ylabel += f"\nper ${pint.Quantity(bin_time, 's').to_compact():~gL}$ interval"
        self.ax.set(ylabel=ylabel)


class TimeFFTPlot(_TimestructurePlotMixin, Xplot):
    def __init__(
        self,
        particles=None,
        what=None,
        *,
        beta=None,
        frev=None,
        fmax=None,
        log=True,
        ax=None,
        mask=None,
        display_units=None,
        plot_kwargs=None,
        scaling="amplitude",
        **subplots_kwargs,
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
                what (str, optional): The particle property to make the FFT over. By default, the FFT is done over the particle count.
                beta: Relativistic beta of particles.
                frev: Revolution frequency of circular line. Use None for linear lines.
                fmax: Maximum frequency (in Hz) to plot.
                log: If True, plot on a log scale.
                ax: An axes to plot onto. If None, a new figure is created.
                mask: An index mask to select particles to plot. If None, all particles are plotted.
                display_units: Dictionary with units for parameters.
                plot_kwargs: Keyword arguments passed to matplotlib.pyplot.plot() plot.
                scaling: Scaling of the FFT. Can be 'amplitude' (default) or 'pds'.
                subplots_kwargs: Keyword arguments passed to matplotlib.pyplot.subplots command when a new figure is created.

        """
        super().__init__(beta, frev, display_units=style(display_units, f="Hz" if log else "kHz"))

        self.fmax = fmax
        self.what = what
        self.scaling = scaling

        # Create plot axes
        if ax is None:
            _, ax = plt.subplots(**subplots_kwargs)
        self.ax = ax
        self.fig = self.ax.figure

        # Create fft plots
        kwargs = style(plot_kwargs, lw=1)
        (self.artist_plot,) = self.ax.plot([], [], **kwargs)
        self.ax.set(
            xlabel="Frequency " + self.label_for("f"),
            xlim=(0, self.fmax * self.factor_for("f")),
        )
        if log:
            self.ax.set(
                xlim=(10 * self.factor_for("f"), self.fmax * self.factor_for("f")),
                xscale="log",
                yscale="log",
            )
        self.ax.grid()

        # set data
        if particles is not None:
            self.update(particles, mask=mask, autoscale=True)

    def update(self, particles, mask=None, autoscale=False):
        """Update plot with new data

        Args:
            particles: Particles data to plot.
            mask: An index mask to select particles to plot. If None, all particles are plotted.
            autoscale: Whether or not to perform autoscaling on all axes.
        """

        # extract times and associated property
        times = self.particle_arrival_times(particles, mask=mask)
        if self.what is None:
            what = None
        else:
            what = self.factor_for(self.what) * get(particles, self.what)
            if mask is not None:
                what = what[mask]

        # re-sample times into equally binned time series
        dt = 1 / 2 / self.fmax
        n = int(np.ceil((np.max(times) - np.min(times)) / dt))
        # to improve FFT performance, round up to next power of 2
        n = 1 << (n - 1).bit_length()
        t_min, dt, timeseries = self.binned_timeseries(times, n, what)

        # calculate fft without DC component
        freq = np.fft.rfftfreq(len(timeseries), d=dt)[1:]
        mag = np.abs(np.fft.rfft(timeseries))[1:]
        if self.scaling.lower() == "amplitude":
            # amplitude in units of particle counts
            self.ax.set(ylabel="FFT amplitude")
            mag *= 2 / len(timeseries)
        elif self.scaling.lower() == "pds":
            # power density spectrum in a.u.
            self.ax.set(ylabel="$|\\mathrm{FFT}|^2$")
            mag = mag**2

        # update plot
        self.artist_plot.set_data(freq * self.factor_for("f"), mag)

        if autoscale:
            self.ax.relim()
            self.ax.autoscale()
            self.ax.set(xlim=(10 * self.factor_for("f"), self.fmax * self.factor_for("f")))

    def plot_harmonics(self, v, dv=0, *, n=20, inverse=False, **plot_kwargs):
        """Add vertical lines or spans indicating the location of values or spans and their harmonics

        Args:
            v (float or list of float): Value or list of values.
            dv (float or list of float, optional): Width or list of widths centered around value(s).
            n (int): Number of harmonics to plot.
            inverse (bool): If true, plot harmonics of n/(v±dv) instead of n*(v±dv). Useful to plot frequency harmonics in time domain and vice-versa.
            plot_kwargs: Keyword arguments to be passed to plotting method
        """
        return super().plot_harmonics(self.ax, v, dv, n=n, inverse=inverse, **plot_kwargs)


class TimeIntervalPlot(_TimestructurePlotMixin, Xplot):
    def __init__(
        self,
        particles=None,
        *,
        beta=None,
        frev=None,
        tmax=None,
        bin_time=None,
        bin_count=None,
        log=True,
        ax=None,
        mask=None,
        display_units=None,
        step_kwargs=None,
        grid=True,
        **subplots_kwargs,
    ):
        """
        A histogram plot of particle arrival intervalls (i.e. delay between consecutive particles).

        The plot is based on the particle arrival time, which is:
            - For circular lines: at_turn / frev - zeta / beta / c0
            - For linear lines: zeta / beta / c0

        Useful to plot time structures of particles loss, such as spill structures.

        Args:
                particles: Particles data to plot.
                beta: Relativistic beta of particles.
                frev: Revolution frequency of circular line. Use None for linear lines.
                tmax: Maximum interval (in s) to plot.
                bin_time: Time bin width if bin_count is None.
                bin_count: Number of bins if bin_time is None.
                log: If True, plot on a log scale.
                ax: An axes to plot onto. If None, a new figure is created.
                mask: An index mask to select particles to plot. If None, all particles are plotted.
                display_units: Dictionary with units for parameters.
                step_kwargs: Keyword arguments passed to matplotlib.pyplot.step() plot.
                grid (bool): En- or disable showing the grid
                subplots_kwargs: Keyword arguments passed to matplotlib.pyplot.subplots command when a new figure is created.

        """
        super().__init__(beta, frev, display_units=style(display_units, f="Hz" if log else "kHz"))

        if bin_time is None and bin_count is None:
            bin_count = 100
        self._bin_time = bin_time
        self._bin_count = bin_count
        self.tmax = tmax

        # Create plot axes
        if ax is None:
            _, ax = plt.subplots(**subplots_kwargs)
        self.ax = ax
        self.fig = self.ax.figure

        # Create distribution plots
        kwargs = style(step_kwargs, lw=1)
        (self.artist_hist,) = self.ax.step([], [], **kwargs)
        self.ax.set(
            xlabel="Delay between consecutive particles " + self.label_for("t"),
            xlim=(self.bin_time if log else 0, self.tmax * self.factor_for("t")),
            ylabel=f"Particles per ${pint.Quantity(self.bin_time, 's').to_compact():~gL}$ bin",
            ylim=(None if log else 0, None),
        )
        self.ax.grid(grid)

        if log:
            self.ax.set(
                xscale="log",
                yscale="log",
            )

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
        times = self.factor_for("t") * self.particle_arrival_times(particles, mask=mask)
        delay = np.diff(sorted(times))

        # calculate and plot histogram
        counts, edges = np.histogram(
            delay, bins=self.bin_count, range=(0, self.bin_count * self.bin_time)
        )
        steps = (np.append(edges, edges[-1]), np.concatenate(([0], counts, [0])))
        self.artist_hist.set_data(steps)

        if autoscale:
            self.ax.relim()
            self.ax.autoscale()

    def plot_harmonics(self, v, dv=0, *, n=20, inverse=False, **plot_kwargs):
        """Add vertical lines or spans indicating the location of values or spans and their harmonics

        Args:
            v (float or list of float): Value or list of values.
            dv (float or list of float, optional): Width or list of widths centered around value(s).
            n (int): Number of harmonics to plot.
            inverse (bool): If true, plot harmonics of n/(v±dv) instead of n*(v±dv). Useful to plot frequency harmonics in time domain and vice-versa.
            plot_kwargs: Keyword arguments to be passed to plotting method
        """
        return super().plot_harmonics(self.ax, v, dv, n=n, inverse=inverse, **plot_kwargs)


class TimeVariationPlot(_TimestructurePlotMixin, Xplot):
    def __init__(
        self,
        particles=None,
        *,
        beta=None,
        frev=None,
        counting_dt=None,
        counting_bins=None,
        evaluate_dt=None,
        evaluate_bins=None,
        metric="cv",
        poisson=True,
        range=None,
        ax=None,
        mask=None,
        display_units=None,
        step_kwargs=None,
        grid=True,
        **subplots_kwargs,
    ):
        """
        Plot of particle arrival time variability.

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
            beta: Relativistic beta of particles.
            frev: Revolution frequency of circular line. If None for linear lines.
            counting_dt: Time bin width for counting if counting_bins is None.
            counting_bins: Number of bins if counting_dt is None.
            metric (str): Metric to plot. See above for list of implemented metrices.
            evaluate_dt: Time bin width for metric evaluation if evaluate_bins is None.
            evaluate_bins: Number of bins if evaluate_dt is None.
            poisson (bool): If true, indicate poisson limit.
            range: A tuple of (min, max) time values defining the histogram range.
            ax: An axes to plot onto. If None, a new figure is created.
            mask: An index mask to select particles to plot. If None, all particles are plotted.
            display_units: Dictionary with units for parameters.
            step_kwargs: Keyword arguments passed to matplotlib.pyplot.step() plot.
            grid (bool): En- or disable showing the grid
            subplots_kwargs: Keyword arguments passed to matplotlib.pyplot.subplots command when a new figure is created.

        """
        super().__init__(beta, frev, display_units=display_units)

        if counting_dt is None and counting_bins is None:
            counting_bins = 100 * 100
        if evaluate_dt is None and evaluate_bins is None:
            evaluate_bins = 100
        self.metric = metric
        self.counting_dt = counting_dt
        self.counting_bins = counting_bins
        self.evaluate_dt = evaluate_dt
        self.evaluate_bins = evaluate_bins
        self.range = range

        # Create plot axes
        if ax is None:
            _, ax = plt.subplots(**subplots_kwargs)
        self.ax = ax
        self.fig = self.ax.figure

        # Create distribution plots
        kwargs = style(step_kwargs, lw=1)
        (self.artist_metric,) = self.ax.step([], [], **kwargs)
        self.ax.set(xlabel=self.label_for("t"), ylim=(0, None))
        self.ax.grid(grid)
        if poisson:
            kwargs.update(
                color=self.artist_metric.get_color() or "gray",
                alpha=0.5,
                zorder=1.9,
                lw=1,
                ls=":",
                label="Poisson limit",
            )
            (self.artist_poisson,) = self.ax.step([], [], **kwargs)
        else:
            self.artist_poisson = None

        # set data
        if particles is not None:
            self.update(particles, mask=mask, autoscale=True)

    def update(self, particles, mask=None, autoscale=False):
        """Update plot with new data

        Args:
            particles: Particles data to plot.
            mask: An index mask to select particles to plot. If None, all particles are plotted.
            autoscale: Whether or not to perform autoscaling on all axes.
        """

        # extract times
        times = self.factor_for("t") * self.particle_arrival_times(particles, mask=mask)

        # histogram
        bin_time = self.counting_dt or (np.max(times) - np.min(times)) / self.counting_bins
        range = self.range or (np.min(times), np.max(times))
        nbins = int(np.ceil((range[1] - range[0]) / bin_time))
        range = (range[0], range[0] + nbins * bin_time)  # ensure exact bin width
        counts, edges = np.histogram(times, bins=nbins, range=range)

        # make 2D array by subdividing into evaluation bins
        if self.evaluate_bins is not None:
            ebins = int(nbins / self.evaluate_bins)
        else:
            ebins = int(self.evaluate_dt / bin_time)
        N = counts = counts[: int(len(counts) / ebins) * ebins].reshape((-1, ebins))
        edges = edges[: int(len(edges) / ebins + 1) * ebins : ebins]

        # calculate metrics
        if self.metric == "cv":
            label = f"Coefficient of variation $c_v=\\sigma/\\mu$"
            F = np.std(N, axis=1) / np.mean(N, axis=1)
            F_poisson = 1 / np.mean(N, axis=1) ** 0.5
        elif self.metric == "duty":
            label = "Spill duty factor $F=\\langle N \\rangle^2/\\langle N^2 \\rangle$"
            F = np.mean(N, axis=1) ** 2 / np.mean(N**2, axis=1)
            F_poisson = 1 / (1 + 1 / np.mean(N, axis=1))
        else:
            raise ValueError(f"Unknown metric {self.metric}")

        # update plot
        steps = (np.append(edges, edges[-1]), np.concatenate(([0], F, [0])))
        self.artist_metric.set_data(steps)
        if self.artist_poisson:
            steps = (np.append(edges, edges[-1]), np.concatenate(([0], F_poisson, [0])))
            self.artist_poisson.set_data(steps)
        self.ax.set(ylabel=label)

        if autoscale:
            self.ax.relim()
            self.ax.autoscale()
            self.ax.set(ylim=(0, None))
