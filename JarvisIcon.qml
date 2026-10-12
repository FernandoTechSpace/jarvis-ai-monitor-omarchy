import QtQuick
import QtQuick.Shapes
import qs.Commons

// HUD mark: a segmented outer ring, an open inner ring and a solid core.
// Drawn as vectors in a single color so it follows the theme like a glyph.
Item {
  id: root

  property real iconSize: Style.bar.iconCanvas
  property color color: Color.foreground
  property bool spinning: false

  width: iconSize
  height: iconSize
  implicitWidth: iconSize
  implicitHeight: iconSize

  readonly property real center: iconSize / 2

  Shape {
    id: outer
    anchors.fill: parent
    preferredRendererType: Shape.CurveRenderer

    Arc { radius: root.iconSize * 0.44; thickness: root.iconSize * 0.1; from: -80; sweep: 100 }
    Arc { radius: root.iconSize * 0.44; thickness: root.iconSize * 0.1; from: 40; sweep: 100 }
    Arc { radius: root.iconSize * 0.44; thickness: root.iconSize * 0.1; from: 160; sweep: 100 }

    RotationAnimator on rotation {
      running: root.spinning
      from: 0
      to: 360
      duration: 6000
      loops: Animation.Infinite
    }
  }

  Shape {
    anchors.fill: parent
    preferredRendererType: Shape.CurveRenderer

    Arc { radius: root.iconSize * 0.25; thickness: root.iconSize * 0.06; from: 135; sweep: 270 }

    ShapePath {
      fillColor: root.color
      strokeWidth: 0
      PathAngleArc {
        centerX: root.center
        centerY: root.center
        radiusX: root.iconSize * 0.1
        radiusY: root.iconSize * 0.1
        startAngle: 0
        sweepAngle: 360
      }
    }
  }

  component Arc: ShapePath {
    property real radius: 0
    property real thickness: 1
    property real from: 0
    property real sweep: 360

    fillColor: "transparent"
    strokeColor: root.color
    strokeWidth: thickness
    capStyle: ShapePath.FlatCap
    PathAngleArc {
      centerX: root.center
      centerY: root.center
      radiusX: radius
      radiusY: radius
      startAngle: from
      sweepAngle: sweep
    }
  }
}
