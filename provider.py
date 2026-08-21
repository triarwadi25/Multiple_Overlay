import os

from qgis.PyQt.QtGui import QIcon

from qgis.core import (
    QgsProcessingProvider,
    QgsProcessingAlgorithm,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterVectorLayer,
    QgsProcessing,
    QgsProcessingException,
    QgsVectorLayer,
    QgsWkbTypes,
    QgsFeature,
    QgsProject,
    QgsProcessingUtils
)


from qgis import processing


def unique_names(names):
    """Return unique field names: FIELD, FIELD_1, FIELD_2..."""
    used = set()
    result = []

    for original in names:
        candidate = original

        if candidate.lower() in used:
            i = 1
            while f"{original}_{i}".lower() in used:
                i += 1
            candidate = f"{original}_{i}"

        used.add(candidate.lower())
        result.append(candidate)

    return result


def make_prepared_layer(source, field_names, suffix):
    """
    Clone a source vector layer into memory while preserving:
    - geometry
    - field definitions
    - field values
    - CRS
    Field names are supplied by prepareLayers().
    """
    geom = QgsWkbTypes.displayString(source.wkbType())
    crs = source.crs()

    uri = f"{geom}?crs={crs.authid()}"

    mem = QgsVectorLayer(
        uri,
        f"overlay_input_{suffix}",
        "memory"
    )

    if not mem.isValid():
        raise QgsProcessingException(
            f"Gagal membuat temporary layer untuk '{source.name()}'."
        )

    provider = mem.dataProvider()

    fields = []

    for i, field in enumerate(source.fields()):
        new_field = field
        new_field.setName(field_names[i])
        fields.append(new_field)

    provider.addAttributes(fields)
    mem.updateFields()

    features = []

    for source_feature in source.getFeatures():
        new_feature = QgsFeature(mem.fields())

        new_feature.setGeometry(
            source_feature.geometry()
        )

        # Explicitly copy attribute values.
        new_feature.setAttributes(
            source_feature.attributes()
        )

        features.append(new_feature)

    if features:
        ok, _ = provider.addFeatures(features)
        if not ok:
            raise QgsProcessingException(
                f"Gagal menyalin fitur dari '{source.name()}'."
            )

    mem.updateExtents()

    return mem


class MultipleOverlayProvider(QgsProcessingProvider):

    def loadAlgorithms(self):
        self.addAlgorithm(IntersectionMultiple())
        self.addAlgorithm(UnionMultiple())
        self.addAlgorithm(ClipMultiple())

    def id(self):
        return "multiple_overlay_tools"

    def name(self):
        return "Multiple Overlay Tools"

    def longName(self):
        return "Multiple Overlay Tools"


class BaseOverlay(QgsProcessingAlgorithm):

    def getLayers(self, parameters, context):
        layers = self.parameterAsLayerList(
            parameters,
            "LAYERS",
            context
        )

        if len(layers) < 2:
            raise QgsProcessingException(
                "Minimal 2 layer polygon harus dipilih."
            )

        for layer in layers:
            if not isinstance(layer, QgsVectorLayer):
                raise QgsProcessingException(
                    "Input harus berupa vector layer."
                )

            if layer.geometryType() != Qgis.GeometryType.Polygon:
                raise QgsProcessingException(
                    f"Layer '{layer.name()}' bukan polygon."
                )

        return layers

    def prepareLayers(self, layers, feedback):
        # Collect every field name from every input layer.
        all_names = []

        for layer in layers:
            all_names.extend(
                [field.name() for field in layer.fields()]
            )

        # Make the complete field list unique before splitting it
        # back to each prepared layer.
        resolved_names = unique_names(all_names)

        prepared = []
        position = 0

        for i, layer in enumerate(layers):
            count = len(layer.fields())

            names = resolved_names[
                position:position + count
            ]

            position += count

            feedback.pushInfo(
                f"Preparing layer {i + 1}/{len(layers)}: "
                f"{layer.name()}"
            )

            prepared.append(
                make_prepared_layer(
                    layer,
                    names,
                    str(i + 1)
                )
            )

        return prepared


class IntersectionMultiple(BaseOverlay):

    def icon(self):
        return QIcon(
            os.path.join(
                os.path.dirname(__file__),
                "icons",
                "intersection.svg"
            )
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                "LAYERS",
                "Input Polygon Layers",
                layerType=QgsProcessing.SourceType.TypeVectorPolygon
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                "OUTPUT",
                "Output Intersection",
                type=QgsProcessing.SourceType.TypeVectorPolygon,
                createByDefault=True,
                defaultValue="TEMPORARY_OUTPUT"
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        layers = self.getLayers(parameters, context)
        prepared = self.prepareLayers(layers, feedback)

        result = processing.run(
            "native:multiintersection",
            {
                "INPUT": prepared[0],
                "OVERLAYS": prepared[1:],
                "OVERLAY_FIELDS_PREFIX": "",
                "OUTPUT": parameters["OUTPUT"]
            },
            context=context,
            feedback=feedback,
            is_child_algorithm=True
        )

        return {
            "OUTPUT": result["OUTPUT"]
        }

    def name(self):
        return "intersection_multiple"

    def displayName(self):
        return "Intersection Multiple"

    def group(self):
        return "Overlay Multiple"

    def groupId(self):
        return "overlay_multiple"

    def createInstance(self):
        return IntersectionMultiple()


class UnionMultiple(BaseOverlay):

    def icon(self):
        return QIcon(
            os.path.join(
                os.path.dirname(__file__),
                "icons",
                "union.svg"
            )
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                "LAYERS",
                "Input Polygon Layers",
                layerType=QgsProcessing.SourceType.TypeVectorPolygon,
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                "OUTPUT",
                "Output Union",
                type=QgsProcessing.SourceType.TypeVectorPolygon,
                createByDefault=True,
                defaultValue="TEMPORARY_OUTPUT"
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        layers = self.getLayers(parameters, context)
        prepared = self.prepareLayers(layers, feedback)

        result = processing.run(
            "native:multiunion",
            {
                "INPUT": prepared[0],
                "OVERLAYS": prepared[1:],
                "OVERLAY_FIELDS_PREFIX": "",
                "OUTPUT": parameters["OUTPUT"]
            },
            context=context,
            feedback=feedback,
            is_child_algorithm=True
        )

        return {
            "OUTPUT": result["OUTPUT"]
        }

    def name(self):
        return "union_multiple"

    def displayName(self):
        return "Union Multiple"

    def group(self):
        return "Overlay Multiple"

    def groupId(self):
        return "overlay_multiple"

    def createInstance(self):
        return UnionMultiple()


class ClipMultiple(QgsProcessingAlgorithm):

    def icon(self):
        return QIcon(
            os.path.join(
                os.path.dirname(__file__),
                "icons",
                "clip.svg"
            )
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                "LAYERS",
                "Input Layers",
                layerType=QgsProcessing.SourceType.TypeVectorAnyGeometry
            )
        )

        self.addParameter(
            QgsProcessingParameterVectorLayer(
                "CLIP",
                "Clip Layer",
                types=[QgsProcessing.SourceType.TypeVectorPolygon]
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        layers = self.parameterAsLayerList(
            parameters,
            "LAYERS",
            context
        )

        clip = self.parameterAsVectorLayer(
            parameters,
            "CLIP",
            context
        )

        if not layers:
            raise QgsProcessingException(
                "Minimal 1 input layer harus dipilih."
            )

        if not clip or not clip.isValid():
            raise QgsProcessingException(
                "Clip Layer tidak valid."
            )

        if clip.geometryType() != Qgis.GeometryType.Polygon:
            raise QgsProcessingException(
                "Clip Layer harus berupa polygon."
            )

        for layer in layers:
            if layer.id() == clip.id():
                raise QgsProcessingException(
                    f"'{layer.name()}' tidak boleh menjadi "
                    "Input Layer sekaligus Clip Layer."
                )

        outputs = []
        total = len(layers)

        for i, layer in enumerate(layers):
            if feedback.isCanceled():
                break

            feedback.setProgress(int(i * 100 / total))

            feedback.pushInfo(
                f"Clipping {i + 1}/{total}: {layer.name()}"
            )

            result = processing.run(
                "native:clip",
                {
                    "INPUT": layer,
                    "OVERLAY": clip,
                    "OUTPUT": "TEMPORARY_OUTPUT"
                },
                context=context,
                feedback=feedback,
                is_child_algorithm=True
            )

            output_id = result["OUTPUT"]
            out_layer = None

            if isinstance(output_id, QgsVectorLayer):
                out_layer = output_id
            else:
                out_layer = context.getMapLayer(output_id)

            if out_layer is None:
                try:
                    out_layer = QgsProcessingUtils.mapLayerFromString(
                        output_id,
                        context,
                        QgsProcessingUtils.LayerHint.Vector
                    )
                except Exception:
                    out_layer = None

            if out_layer is None or not out_layer.isValid():
                raise QgsProcessingException(
                    f"Gagal mengambil temporary output untuk "
                    f"'{layer.name()}'. ID output: {output_id}"
                )

            out_layer.setName(
                f"{layer.name()}_clip"
            )

            if QgsProject.instance().mapLayer(out_layer.id()) is None:
                QgsProject.instance().addMapLayer(
                    out_layer,
                    True
                )

            outputs.append(out_layer.id())

            feedback.pushInfo(
                f"Output ditambahkan ke project: "
                f"{out_layer.name()}"
            )

        feedback.setProgress(100)

        feedback.pushInfo(
            f"Clip Multiple selesai: {len(outputs)} output temporary "
            "telah ditambahkan ke project."
        )

        return {
            "OUTPUTS": outputs
        }

    def name(self):
        return "clip_multiple"

    def displayName(self):
        return "Clip Multiple"

    def group(self):
        return "Overlay Multiple"

    def groupId(self):
        return "overlay_multiple"

    def createInstance(self):
        return ClipMultiple()
