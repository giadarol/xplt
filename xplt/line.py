#!/usr/bin/env python3
# -*- coding: utf-8 -*-

""" Methods for plotting lines

"""

__author__ = "Philipp Niedermayer"
__contact__ = "eltos@outlook.de"
__date__ = "2022-11-08"

import re
import types

import matplotlib as mpl
import numpy as np

from .base import XPlot, XManifoldPlot
from .util import defaults, get, defaults_for
from .properties import Property, DataProperty


def iter_elements(line):
    """Iterate over elements in line

    Args:
        line (xtrack.Line): Line of elements.

    Yields:
        (name, element, s_from, s_to): Name, element, start and end s position of element.

    """
    el_s0 = line.get_s_elements("upstream")
    el_s1 = line.get_s_elements("downstream")
    for name, el, s0, s1 in zip(line.element_names, line.elements, el_s0, el_s1):
        if s0 == s1:  # thin lense located at element center
            if hasattr(el, "length"):
                s0, s1 = (s0 + s1 - el.length) / 2, (s0 + s1 + el.length) / 2
        yield name, el, s0, s1


def order(knl):
    """Get order of knl string as int"""
    return int(re.match(r"k(\d+)l", knl).group(1))


class KnlPlot(XManifoldPlot):
    """A plot for knl values along line"""

    def __init__(
        self, line=None, *, knl=None, filled=True, resolution=1000, line_length=None, **kwargs
    ):
        """

        Args:
            line (xtrack.Line): Line of elements.
            knl (int | list[int] | str): Maximum order or list of orders n to plot knl values for.
                This can also be a manifold subplot specification string like ``"k0l+k1l,k2l"``,
                see :class:`~.base.XManifoldPlot` for details.
                If None, automatically determine from line.
            filled (bool): If True, make a filled plot instead of a line plot.
            resolution (int): Number of points to use for plot.
            line_length (float, optional): Length of line (only required if line is None).
            kwargs: See :class:`~.base.XPlot` for additional arguments

        Known issues:
            - Thin elements produced with MAD-X MAKETHIN do overlap due to the displacement introduced by the TEAPOT algorithm.
              This leads to glitches of knl being doubled or zero at element overlaps for lines containing such elements.

        """

        if knl is None:
            if line is None:
                raise ValueError("Either line or knl parameter must not be None")
            knl = range(max([e.order for e in line.elements if hasattr(e, "order")]) + 1)
        if isinstance(knl, int):
            knl = range(knl + 1)
        if not isinstance(knl, str):
            knl = [[[f"k{n}l" for n in knl]]]
        if line is None and line_length is None:
            raise ValueError("Either line or line_length parameter must not be None")
        self.S = np.linspace(0, line_length or line.get_length(), resolution)
        self.filled = filled

        super().__init__(on_x="s", on_y=knl, **kwargs)

        # create plot elements
        def create_artists(i, j, k, a, p):
            kwargs = dict(color=f"C{order(p)}", alpha=0.5, label=self.label_for(p, unit=True))
            if self.filled:
                return a.fill_between(self.S, np.zeros_like(self.S), zorder=3, lw=0, **kwargs)
            else:
                return a.plot([], [], **kwargs)[0]

        self._create_artists(create_artists)

        for a in self.axflat:
            a.plot(self.S, np.zeros_like(self.S), "k-", lw=1, zorder=4)
        self.legend(show="auto", ncol=5)

        # set data
        if line is not None:
            self.update(line, autoscale=True)

    def update(self, line, autoscale=False):
        """
        Update the line data this plot shows

        Args:
            line (xtrack.Line): Line of elements.
            autoscale (bool): Whether or not to perform autoscaling on all axes

        Returns:
            changed artists
        """
        # compute knl as function of s
        values = {p: np.zeros(self.S.size) for p in self.on_y_unique}
        orders = {p: order(p) for p in self.on_y_unique}
        Smax = line.get_length()
        for name, el, s0, s1 in iter_elements(line):
            if hasattr(el, "knl"):
                if 0 <= s0 <= Smax:
                    mask = (self.S >= s0) & (self.S < s1)
                else:
                    # handle wrap around
                    mask = (self.S >= s0 % Smax) | (self.S < s1 % Smax)
                for knl, n in orders.items():
                    if n <= el.order:
                        values[knl][mask] += el.knl[n]

        # plot
        s = self.S * self.factor_for("s")
        changed = []
        for i, ppp in enumerate(self.on_y):
            for j, pp in enumerate(ppp):
                for k, p in enumerate(pp):
                    art = self.artists[i][j][k]
                    y = self.factor_for(p) * values[p]
                    if self.filled:
                        art.get_paths()[0].vertices[1 : 1 + y.size, 1] = y
                    else:
                        art.set_data((s, y))
                    changed.append(art)

                if autoscale:
                    ax = self.axis(i, j)
                    if self.filled:  # At present, relim does not support collection instances.
                        ax.update_datalim(
                            mpl.transforms.Bbox.union(
                                [a.get_datalim(ax.transData) for a in self.artists[i][j]]
                            )
                        )
                    else:
                        ax.relim()
                    ax.autoscale()
                    ax.set(xlim=(np.min(s), np.max(s)))

        return changed

    def prop(self, p):
        if match := re.fullmatch(r"k(\d+)l", p):
            n = match.group(1)
            return Property(symbol=f"$k_{n}l$", unit="rad" if n == "0" else f"m^-{n}")
        return super().prop(p)

    def label_for(self, *pp, unit=True, description=True):
        """
        Return axis label for list of properties, joining where possible

        Args:
            pp: Property names
            unit (bool): Whether to include unit
            description (bool): Whether to include description

        Returns:
            str: Axis label
        """
        if len(pp) > 1 and np.all([re.match(r"k\d+l", p) for p in pp]):
            label = "$k_nl$"
            if unit:
                label += " / $m^{-n}$"
            return label
        return super().label_for(*pp, unit=unit, description=description)


class FloorPlot(XPlot):
    """A floor plan of the line based on survey data"""

    def __init__(
        self,
        survey=None,
        line=None,
        projection="ZX",
        *,
        boxes=None,
        labels=False,
        ignore=None,
        element_width=1,
        **kwargs,
    ):
        """

        Args:
            survey (Any): Survey data.
            projection (str): The projection to use: A pair of coordinates ('XZ', 'ZY' etc.)
            line (xtrack.Line): Line data with additional information about elements.
                Use this to have colored boxes of correct size etc.
            boxes (None | bool | str | iterable | dict): Config option for showing colored boxes for elements. See below.
                Detailed options can be "length" and all options suitable for a patch,
                such as "color", "alpha", etc.
            labels (None | bool | str | iterable | dict): Config option for showing labels for elements. See below.
                Detailed options can be "text" (e.g. "Dipole {name}" where name will be
                replaced with the element name) and all options suitable for an annotation,
                such as "color", "alpha", etc.
            ignore (None | str | list[str]): Optional patter or list of patterns to ignore elements with matching names.
            element_width (float): Width of element boxes.
            kwargs: See :class:`~.base.XPlot` for additional arguments


        The config options passed to boxes and labels can be:
            - None: Use good defaults.
            - A bool: En-/disable option for all elements (except drifts).
            - A str (regex): Filter by element name.
            - A list, tuple or numpy array: Filter by any of the given element names
            - A dict: Detailed options to apply for each element in the form of
              `{"regex": {...}}`. For each matching element name, the options are used.

        """

        kwargs["_properties"] = defaults(
            kwargs.get("_properties"),
            X=DataProperty("X", "m"),
            Y=DataProperty("Y", "m"),
            Z=DataProperty("Z", "m"),
            theta=DataProperty("theta", "rad", "$\\Theta$"),
            phi=DataProperty("phi", "rad", "$\\Phi$"),
            psi=DataProperty("psi", "rad", "$\\Psi$"),
        )

        super().__init__(**kwargs)

        if projection == "3D":
            raise NotImplementedError()

        self.projection = projection
        self.boxes = boxes
        self.labels = labels
        self.ignore = [ignore] if isinstance(ignore, str) else ignore
        self.element_width = element_width

        if isinstance(self.boxes, (list, tuple, np.ndarray)):
            self.boxes = "|".join(["^" + ll + "$" for ll in self.boxes])
        if isinstance(self.labels, (list, tuple, np.ndarray)):
            self.labels = "|".join(["^" + ll + "$" for ll in self.labels])

        # Create plot
        self.ax.set(
            xlabel=self.label_for(self.projection[0]), ylabel=self.label_for(self.projection[1])
        )
        self.ax.axis("equal")

        # create plot elements
        (self.artist_beamline,) = self.ax.plot([], [], "k-")
        self.artist_startpoint = mpl.patches.FancyArrowPatch(
            (0, 0), (0, 0), mutation_scale=20, color="k", arrowstyle="-|>", zorder=5, lw=0
        )
        self.ax.add_patch(self.artist_startpoint)
        self.artists_boxes = []
        self.artists_labels = []

        # set data
        if survey is not None:
            self.update(survey, line, autoscale=True)

    def update(self, survey, line=None, autoscale=False):
        """
        Update the survey data this plot shows

        Args:
            survey (Any): Survey data.
            line (None | xtrack.Line): Line data.
            autoscale (bool): Whether or not to perform autoscaling on all axes

        Returns:
            changed artists

        """

        changed = []

        if self.projection == "3D":
            ...
            raise NotImplementedError()

        else:
            A, B = self.projection
            scale = self.factor_for(A)
            if scale != self.factor_for(B):
                # can't handle this, because angles are not preserved
                raise ValueError(f"Display units for {A} and {B} must be equal!")

            X = get(survey, A) * scale
            Y = get(survey, B) * scale
            # ang: transform angles from data (A-B) to axis (X-Y) coordinate system
            if self.projection == "ZX":
                R = get(survey, "theta")
                ang = lambda a: a
            elif self.projection == "XZ":
                R = get(survey, "theta")
                ang = lambda a: np.pi / 2 - a
            else:
                ...
                raise NotImplementedError()

            NAME = get(survey, "name")
            BEND = get(survey, "angle")

            # beam line
            ############
            self.artist_beamline.set_data(X, Y)
            changed.append(self.artist_beamline)
            # start point arrow
            i = np.argmax((X > X[0]) | (Y > Y[0]))
            self.artist_startpoint.set_positions((2 * X[0] - X[i], 2 * Y[0] - Y[i]), (X[0], Y[0]))
            changed.append(self.artist_startpoint)

            # elements
            ###########
            while len(self.artists_boxes) > 0:
                # remove old artists
                self.artists_boxes.pop().remove()

            while len(self.artists_labels) > 0:
                # remove old artists
                self.artists_labels.pop().remove()

            helicity = 1
            legend_entries = []
            for i, (x, y, rt, name, arc) in enumerate(zip(X, Y, R, NAME, BEND)):
                drift_length = get(survey, "drift_length", None)
                is_thick = line is not None and name in line.element_dict and line[name].isthick
                if drift_length is not None and drift_length[i] > 0 and not is_thick:
                    continue  # skip drift spaces
                if self.ignore is not None:
                    if np.any([re.match(pattern, name) is not None for pattern in self.ignore]):
                        continue  # skip ignored

                helicity = np.sign(arc) or helicity
                # rt = angle of tangential direction in data coords
                # rr = angle of radial direction (outward) in axis coords
                rr = ang(rt - arc / 2 + helicity * np.pi / 2)

                element = line.element_dict.get(name) if line is not None else None
                order = get(element, "order", None)
                order = get(survey, "order", {i: order})[i]
                if line is not None and name in line.element_dict:
                    order = ORDER_NAMED_ELEMENTS.get(line[name].__class__.__name__, order)

                length = get(element, "length", None)
                length = get(survey, "length", {i: length})[i]
                if length is not None:
                    length = length * scale

                # box
                ######

                box_style = {}
                if order is not None:
                    box_style["color"] = f"C{order}"
                if length is not None:
                    box_style["length"] = length

                # legend label
                box_style["label"] = {
                    0: "Bending magnet" if arc else None,
                    1: "Quadrupole magnet",
                    2: "Sextupole magnet",
                    3: "Octupole magnet",
                }.get(order)

                boxes = self.boxes
                if boxes is None:
                    boxes = line is None or order is not None
                box_style = self._get_config(boxes, name, **box_style)

                if box_style is not None:
                    width = box_style.pop("width", self.element_width * scale)
                    length = box_style.pop("length", 0)
                    if box_style.get("label") in legend_entries:
                        box_style.pop("label")  # prevent duplicate legend entries
                    else:
                        legend_entries.append(box_style.get("label"))

                    # Handle thick elements
                    if is_thick and i + 1 < len(X):
                        # Find the center of the arc
                        x_mid = 0.5 * (x + X[i + 1])
                        y_mid = 0.5 * (y + Y[i + 1])
                        dr = np.array([X[i + 1] - x, Y[i + 1] - y, 0])
                        dn = np.cross(dr, [0, 0, 1])
                        dn /= np.linalg.norm(dn)
                        d = np.linalg.norm(dr) / 2
                        sin_theta = np.abs(d * arc / length)
                        dh = d * sin_theta
                        p_center = np.array([x_mid, y_mid, 0]) - helicity * dh * dn
                        x = p_center[0]
                        y = p_center[1]

                    if length > 0 and arc:
                        # bending elements as wedge
                        rho = length / arc
                        box = mpl.patches.Wedge(
                            **defaults_for(
                                mpl.patches.Wedge,
                                box_style,
                                center=(
                                    x - helicity * rho * np.cos(rr) / np.cos(arc / 2),
                                    y - helicity * rho * np.sin(rr) / np.cos(arc / 2),
                                ),
                                r=rho + width / 2,
                                width=width,
                                theta1=np.rad2deg(rr - helicity * arc / 2)
                                + 90 * (1 - helicity),  # rr - arc/2),
                                theta2=np.rad2deg(rr + helicity * arc / 2)
                                + 90 * (1 - helicity),  # rr + arc/2),
                                alpha=0.5,
                                zorder=3,
                            )
                        )

                    else:
                        # other elements as rect
                        box = mpl.patches.Rectangle(
                            **defaults_for(
                                mpl.patches.Rectangle,
                                box_style,
                                xy=(x - width / 2, y - length / 2),
                                width=width,
                                height=length or (0.1 * scale),
                                angle=np.rad2deg(ang(rt - arc / 2)) - 90,
                                rotation_point="center",
                                alpha=0.5,
                                zorder=3,
                            )
                        )
                    self.ax.add_patch(box)
                    self.artists_boxes.append(box)
                    changed.append(box)

                # label
                ########

                labels = self.labels
                if labels is None:
                    labels = line is not None and order is not None
                label_style = self._get_config(labels, name, text=name)

                if label_style is not None:
                    width = label_style.pop("width", self.element_width * scale)
                    label_style["text"] = label_style["text"].format(name=name, element=element)

                    label = self.ax.annotate(
                        **defaults_for(
                            "text",
                            label_style,
                            xy=(x, y),
                            xytext=(x + 1.5 * width * np.cos(rr), y + 1.5 * width * np.sin(rr)),
                            # xytext=(40*np.cos(rr), 40*np.sin(rr)),
                            # textcoords='offset points',
                            va={1: "bottom", 0: "center", -1: "top"}[np.round(np.sin(rr))],
                            ha={1: "left", 0: "center", -1: "right"}[np.round(np.cos(rr))],
                            # rotation=(np.rad2deg(rr)+90)%180-90,
                            arrowprops=dict(arrowstyle="-", color="0.5", shrinkB=5),
                            clip_on=True,
                            zorder=5,
                        )
                    )
                    self.artists_labels.append(label)
                    changed.append(label)

            if autoscale:
                self.ax.relim()
                datalim = self.ax.dataLim
                self.fig.canvas.draw()  # required to get window extend
                for artist in self.artists_boxes + self.artists_labels:
                    bbox = artist.get_window_extent()
                    datalim = mpl.transforms.Bbox.union(
                        (datalim, bbox.transformed(self.ax.transData.inverted()))
                    )

                self.ax.update_datalim(datalim)
                self.ax.autoscale()

        return changed

    def legend(self, **kwargs):
        self.ax.legend(**kwargs)

    def add_scale(self, scale=None, label=None, *, loc="auto", color="k", fontsize="x-small"):
        """Add a scale patch (a yardstick or ruler)

        Args:
            scale (float): The length of the scale in data units (typically meter).
            label (str | None): A label for the scale.
            loc (str): The location of the scale. Can be any of the usual matplotlib locations, e.g. 'auto', 'upper left', 'upper center', 'upper right', 'center left', 'center', 'center right', 'lower left', 'lower center, 'lower right'.
            color (Any): Color for the patch.
            fontsize (Any): Font size of the label.

        Returns:
            The artist added (an AnchoredOffsetbox).
        """
        if scale is None:
            scale = 5
        else:
            # convert to display units
            scale = scale * self.factor_for(self.projection[0])

        if label is None:
            unit = self.display_unit_for(self.projection[0])
            label = f"{scale:g} {unit}"

        return super().add_scale(
            self.ax, scale, label=label, loc=loc, color=color, fontsize=fontsize
        )

    @staticmethod
    def _get_config(config, name, **default):
        if isinstance(config, str):
            if re.match(config, name):
                return default
        elif isinstance(config, dict):
            for pattern, args in config.items():
                if re.match(pattern, name):
                    if args is False:
                        return None
                    if isinstance(args, dict):
                        return defaults(args, **default)
                    return default
        elif config:
            return default


# Known class names from xtrack and their order
ORDER_NAMED_ELEMENTS = {
    "Bend": 0,
    "Quadrupole": 1,
    "Sextupole": 2,
    "Octupole": 3,
}

## Restrict star imports to local namespace
__all__ = [
    name
    for name, thing in globals().items()
    if not (name.startswith("_") or isinstance(thing, types.ModuleType))
]
