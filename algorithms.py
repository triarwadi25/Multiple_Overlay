# -*- coding: utf-8 -*-
"""Processing algorithms of Multiple Overlay Tools."""
import os
import re

from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingMultiStepFeedback,
    QgsProcessingOutputMultipleLayers,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterDefinition,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterString,
    QgsProject,
    QgsVectorLayer,
)

from .engine import (
    KIND_NAMES,
    as_layer,
    fix_geometries,
    geometry_kind,
    parse_config,
    prepare_layer,
    prepare_overlay,
    run_child,
    source_reference,
)

ICON_DIR = os.path.join(os.path.dirname(__file__), "icons")

CONFIG_HELP = (
    "<p><b>Per-layer settings (advanced)</b>: a JSON list with one entry per "
    "input layer, in the same order as the input layers, for example:<br>"
    "<code>[{\"selected_only\": true, \"prefix\": \"a_\", \"fields\": "
    "[\"id\", \"name\"]}, {\"prefix\": \"b_\"}]</code><br>"
    "<code>fields</code> = null or missing keeps every field. The menu "
    "dialog (Vector &gt; Overlay Multiple) builds this for you.</p>"
)


class BaseOverlay(QgsProcessingAlgorithm):
    """Shared behaviour of the four algorithms."""

    MIN_LAYERS = 2
    ICON = "overlay_multiple.svg"

    # ---- metadata ---------------------------------------------------
    def icon(self):
        return QIcon(os.path.join(ICON_DIR, self.ICON))

    def group(self):
        return "Overlay Multiple"

    def groupId(self):
        return "overlay_multiple"

    def flags(self):
        # Project layers are read directly, so run in the main thread.
        return super().flags() | QgsProcessingAlgorithm.FlagNoThreading

    def tags(self):
        return ["overlay", "multiple", "batch", "vector"]

    # ---- parameters -------------------------------------------------
    def add_common_parameters(self, layers_label):
        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                "LAYERS",
                layers_label,
                layerType=QgsProcessing.TypeVectorAnyGeometry,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                "FIX_GEOMETRIES",
                "Fix invalid geometries before processing",
                defaultValue=True,
            )
        )
        config = QgsProcessingParameterString(
            "CONFIG",
            "Per-layer settings (JSON)",
            optional=True,
            multiLine=True,
        )
        config.setFlags(
            config.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(config)

    # ---- input handling ---------------------------------------------
    def load_inputs(self, parameters, context):
        layers = self.parameterAsLayerList(parameters, "LAYERS", context)

        if len(layers) < self.MIN_LAYERS:
            raise QgsProcessingException(
                "Select at least {} layers.".format(self.MIN_LAYERS))

        kinds = []
        for layer in layers:
            if not isinstance(layer, QgsVectorLayer):
                raise QgsProcessingException(
                    "'{}' is not a vector layer.".format(layer.name()))
            kind = geometry_kind(layer)
            if kind is None:
                raise QgsProcessingException(
                    "Layer '{}' has no geometry.".format(layer.name()))
            kinds.append(kind)

        configs = parse_config(
            self.parameterAsString(parameters, "CONFIG", context),
            len(layers),
        )
        return layers, kinds, configs

    def validate(self, layers, kinds, configs):
        """Algorithm specific checks; raise QgsProcessingException."""

    def checkParameterValues(self, parameters, context):
        try:
            layers, kinds, configs = self.load_inputs(parameters, context)
            self.validate(layers, kinds, configs)
        except QgsProcessingException as exc:
            return False, str(exc)
        return True, ""

    def fix_enabled(self, parameters, context):
        return bool(self.parameterAsBool(parameters, "FIX_GEOMETRIES", context))

    def createInstance(self):
        return self.__class__()


# ======================================================== Intersection ===

class IntersectionMultiple(BaseOverlay):
    ICON = "intersection.svg"

    def name(self):
        return "intersection_multiple"

    def displayName(self):
        return "Intersection Multiple"

    def shortHelpString(self):
        return (
            "<p>Intersects two or more vector layers in one run. Layers may "
            "be points, lines or polygons and can be mixed.</p>"
            "<p>Layers are processed from the lowest to the highest geometry "
            "dimension (points, then lines, then polygons), so the result "
            "keeps the geometry type of the lowest-dimension layer. Field "
            "order in the output follows this processing order.</p>"
            "<p>Per layer you can use selected features only, keep only "
            "chosen fields and add a field-name prefix. Field names are "
            "always made unique.</p>" + CONFIG_HELP
        )

    def initAlgorithm(self, config=None):
        self.add_common_parameters("Input layers")
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                "OUTPUT",
                "Output Intersection",
                type=QgsProcessing.TypeVectorAnyGeometry,
                createByDefault=True,
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        layers, kinds, configs = self.load_inputs(parameters, context)
        self.validate(layers, kinds, configs)
        fix = self.fix_enabled(parameters, context)

        count = len(layers)
        steps = QgsProcessingMultiStepFeedback(2 * count - 1, feedback)

        used = set()
        references = []
        for i, layer in enumerate(layers):
            if feedback.isCanceled():
                return {}
            steps.setCurrentStep(i)
            feedback.pushInfo("Preparing layer {}/{}: {} ({})".format(
                i + 1, count, layer.name(), KIND_NAMES[kinds[i]]))
            references.append(
                prepare_layer(layer, configs[i], used, context, steps, fix))

        order = sorted(range(count), key=lambda i: (kinds[i], i))
        current = references[order[0]]
        output = None

        for step, index in enumerate(order[1:]):
            if feedback.isCanceled():
                return {}
            steps.setCurrentStep(count + step)
            feedback.pushInfo("Intersecting with: {}".format(
                layers[index].name()))
            last = step == len(order) - 2
            result = run_child(
                "native:intersection",
                {
                    "INPUT": current,
                    "OVERLAY": references[index],
                    "OUTPUT": parameters["OUTPUT"] if last else "memory:",
                },
                context,
                steps,
            )
            if last:
                output = result["OUTPUT"]
            else:
                current = as_layer(result["OUTPUT"], context).id()

        return {"OUTPUT": output}


# ============================================================== Union ====

class UnionMultiple(BaseOverlay):
    ICON = "union.svg"

    def name(self):
        return "union_multiple"

    def displayName(self):
        return "Union Multiple"

    def shortHelpString(self):
        return (
            "<p>Unions two or more vector layers in one run. QGIS' union "
            "needs identical geometry types, so all layers must be points, "
            "or all lines, or all polygons.</p>"
            "<p>Per layer you can use selected features only, keep only "
            "chosen fields and add a field-name prefix. Field names are "
            "always made unique.</p>" + CONFIG_HELP
        )

    def validate(self, layers, kinds, configs):
        if len(set(kinds)) > 1:
            raise QgsProcessingException(
                "Union needs layers of the same geometry type; got: {}."
                .format(", ".join(
                    "{} ({})".format(l.name(), KIND_NAMES[k])
                    for l, k in zip(layers, kinds))))

    def initAlgorithm(self, config=None):
        self.add_common_parameters("Input layers")
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                "OUTPUT",
                "Output Union",
                type=QgsProcessing.TypeVectorAnyGeometry,
                createByDefault=True,
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        layers, kinds, configs = self.load_inputs(parameters, context)
        self.validate(layers, kinds, configs)
        fix = self.fix_enabled(parameters, context)

        count = len(layers)
        steps = QgsProcessingMultiStepFeedback(2 * count - 1, feedback)

        used = set()
        references = []
        for i, layer in enumerate(layers):
            if feedback.isCanceled():
                return {}
            steps.setCurrentStep(i)
            feedback.pushInfo("Preparing layer {}/{}: {}".format(
                i + 1, count, layer.name()))
            references.append(
                prepare_layer(layer, configs[i], used, context, steps, fix))

        current = references[0]
        output = None
        for step, reference in enumerate(references[1:]):
            if feedback.isCanceled():
                return {}
            steps.setCurrentStep(count + step)
            feedback.pushInfo("Union with: {}".format(
                layers[step + 1].name()))
            last = step == count - 2
            result = run_child(
                "native:union",
                {
                    "INPUT": current,
                    "OVERLAY": reference,
                    "OUTPUT": parameters["OUTPUT"] if last else "memory:",
                },
                context,
                steps,
            )
            if last:
                output = result["OUTPUT"]
            else:
                current = as_layer(result["OUTPUT"], context).id()

        return {"OUTPUT": output}


# ============================================================== Erase ====

class EraseMultiple(BaseOverlay):
    ICON = "erase.svg"

    def name(self):
        return "erase_multiple"

    def displayName(self):
        return "Erase Multiple"

    def shortHelpString(self):
        return (
            "<p>Removes from the <b>first</b> layer (point, line or polygon) "
            "the parts that overlap <b>any of the other layers</b>, which "
            "must be polygons. It is the difference operation repeated for "
            "every erase layer.</p>"
            "<p>Field selection and prefix apply to the first layer only; "
            "'selected features only' can be set for every layer.</p>"
            + CONFIG_HELP
        )

    def validate(self, layers, kinds, configs):
        for layer, kind in zip(layers[1:], kinds[1:]):
            if kind != 2:
                raise QgsProcessingException(
                    "Erase layer '{}' must be a polygon layer.".format(
                        layer.name()))

    def initAlgorithm(self, config=None):
        self.add_common_parameters(
            "Layers (first = layer to erase from, others = erase polygons)")
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                "OUTPUT",
                "Output Erase",
                type=QgsProcessing.TypeVectorAnyGeometry,
                createByDefault=True,
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        layers, kinds, configs = self.load_inputs(parameters, context)
        self.validate(layers, kinds, configs)
        fix = self.fix_enabled(parameters, context)

        count = len(layers)
        steps = QgsProcessingMultiStepFeedback(2 * count - 1, feedback)

        feedback.pushInfo("Preparing base layer: {}".format(layers[0].name()))
        steps.setCurrentStep(0)
        current = prepare_layer(
            layers[0], configs[0], set(), context, steps, fix)

        overlays = []
        for i in range(1, count):
            if feedback.isCanceled():
                return {}
            steps.setCurrentStep(i)
            feedback.pushInfo("Preparing erase layer: {}".format(
                layers[i].name()))
            overlays.append(prepare_overlay(
                layers[i], configs[i].selected_only, fix, context, steps))

        output = None
        for step, overlay in enumerate(overlays):
            if feedback.isCanceled():
                return {}
            steps.setCurrentStep(count + step)
            feedback.pushInfo("Erasing with: {}".format(
                layers[step + 1].name()))
            last = step == len(overlays) - 1
            result = run_child(
                "native:difference",
                {
                    "INPUT": current,
                    "OVERLAY": overlay,
                    "OUTPUT": parameters["OUTPUT"] if last else "memory:",
                },
                context,
                steps,
            )
            if last:
                output = result["OUTPUT"]
            else:
                current = as_layer(result["OUTPUT"], context).id()

        return {"OUTPUT": output}


# =============================================================== Clip ====

def _safe_file_name(name):
    cleaned = re.sub(r'[\\/:*?"<>|\s]+', "_", name).strip("_")
    return cleaned or "layer"


class ClipMultiple(BaseOverlay):
    MIN_LAYERS = 1
    ICON = "clip.svg"
    FORMATS = [("GeoPackage (.gpkg)", ".gpkg"), ("Shapefile (.shp)", ".shp")]

    def name(self):
        return "clip_multiple"

    def displayName(self):
        return "Clip Multiple"

    def shortHelpString(self):
        return (
            "<p>Clips several layers (points, lines or polygons) with one "
            "polygon layer.</p>"
            "<p>Leave the output folder empty to get temporary layers added "
            "to the project; otherwise one file per layer is written to the "
            "folder (existing files with the same name are overwritten)."
            "</p><p>'Selected features only' can be set per input layer; "
            "use the checkbox of the clip layer parameter for the clip "
            "layer.</p>" + CONFIG_HELP
        )

    def initAlgorithm(self, config=None):
        self.add_common_parameters("Input layers")
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                "CLIP",
                "Clip layer",
                [QgsProcessing.TypeVectorPolygon],
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                "OUTPUT_FORMAT",
                "Output format (when writing to a folder)",
                options=[label for label, _ in self.FORMATS],
                defaultValue=0,
            )
        )
        self.addParameter(
            QgsProcessingParameterFolderDestination(
                "OUTPUT_FOLDER",
                "Output folder (empty = temporary layers)",
                optional=True,
                createByDefault=False,
            )
        )
        self.addOutput(
            QgsProcessingOutputMultipleLayers("OUTPUTS", "Clipped layers"))

    def validate(self, layers, kinds, configs):
        pass

    def processAlgorithm(self, parameters, context, feedback):
        layers, kinds, configs = self.load_inputs(parameters, context)
        fix = self.fix_enabled(parameters, context)

        clip_layer = self.parameterAsVectorLayer(parameters, "CLIP", context)
        if clip_layer is None:
            raise QgsProcessingException("Clip layer is not valid.")
        if geometry_kind(clip_layer) != 2:
            raise QgsProcessingException("Clip layer must be a polygon layer.")
        for layer in layers:
            if layer.id() == clip_layer.id():
                raise QgsProcessingException(
                    "'{}' cannot be an input layer and the clip layer at the "
                    "same time.".format(layer.name()))

        clip_reference = parameters["CLIP"]
        if fix:
            clip_reference = fix_geometries(clip_reference, context, feedback)

        folder = self.parameterAsString(
            parameters, "OUTPUT_FOLDER", context).strip()
        extension = self.FORMATS[
            self.parameterAsEnum(parameters, "OUTPUT_FORMAT", context)][1]
        if folder:
            os.makedirs(folder, exist_ok=True)

        project = context.project() or QgsProject.instance()
        total = len(layers)
        outputs = []
        used_names = set()

        for i, layer in enumerate(layers):
            if feedback.isCanceled():
                break
            feedback.setProgress(int(i * 100 / total))
            feedback.pushInfo("Clipping {}/{}: {}".format(
                i + 1, total, layer.name()))

            reference = source_reference(layer, configs[i].selected_only)
            if fix and geometry_kind(layer) in (1, 2):
                reference = fix_geometries(reference, context, feedback)

            base = _safe_file_name("{}_clip".format(layer.name()))
            file_name = base
            counter = 1
            while file_name.lower() in used_names:
                file_name = "{}_{}".format(base, counter)
                counter += 1
            used_names.add(file_name.lower())

            destination = (
                os.path.join(folder, file_name + extension)
                if folder else "memory:"
            )
            result = run_child(
                "native:clip",
                {
                    "INPUT": reference,
                    "OVERLAY": clip_reference,
                    "OUTPUT": destination,
                },
                context,
                feedback,
            )

            display_name = "{}_clip".format(layer.name())
            if folder:
                identifier = result["OUTPUT"]
            else:
                out_layer = as_layer(result["OUTPUT"], context)
                out_layer.setName(display_name)
                identifier = out_layer.id()

            context.addLayerToLoadOnCompletion(
                identifier,
                QgsProcessingContext.LayerDetails(
                    display_name, project, "OUTPUTS"),
            )
            outputs.append(identifier)

        feedback.setProgress(100)
        feedback.pushInfo("Clip Multiple finished: {} layer(s).".format(
            len(outputs)))
        return {"OUTPUTS": outputs}
