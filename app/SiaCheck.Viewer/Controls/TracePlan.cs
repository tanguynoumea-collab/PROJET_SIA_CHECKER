using System.Globalization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using Clipper2Lib;
using SiaCheck.Viewer.Scene;
using SiaCheck.Viewer.ViewModels;

namespace SiaCheck.Viewer.Controls;

/// <summary>
/// Plan d'un niveau pour le module de tracé (plan, Évolution 2.1). Dessine les surfaces aux couleurs SIA
/// (aplats pâles), la surface source en contour épais, l'emprise du niveau inférieur en pointillé, puis le tracé
/// à l'accent (aplat de l'aire comptée et liseré des polygones dessinés). Gère les gestes du tracé ; toute la
/// géométrie et les chiffres sont dans <see cref="TraceSession"/>.
///
/// Repère : mètres du fichier visionneuse (y vers le haut) → pixels (y vers le bas).
/// </summary>
public sealed class TracePlan : FrameworkElement
{
    public static readonly DependencyProperty SessionProperty = DependencyProperty.Register(
        nameof(Session), typeof(TraceSession), typeof(TracePlan),
        new FrameworkPropertyMetadata(null, FrameworkPropertyMetadataOptions.AffectsRender, (d, e) => ((TracePlan)d).OnSession(e)));
    public static readonly DependencyProperty PaletteProperty = DependencyProperty.Register(
        nameof(Palette), typeof(SiaPalette), typeof(TracePlan), new FrameworkPropertyMetadata(null, FrameworkPropertyMetadataOptions.AffectsRender));
    public static readonly DependencyProperty AccentProperty = DependencyProperty.Register(
        nameof(Accent), typeof(Brush), typeof(TracePlan), new FrameworkPropertyMetadata(Brushes.SlateBlue, FrameworkPropertyMetadataOptions.AffectsRender));
    public static readonly DependencyProperty PrimaryProperty = DependencyProperty.Register(
        nameof(Primary), typeof(Brush), typeof(TracePlan), new FrameworkPropertyMetadata(Brushes.Black, FrameworkPropertyMetadataOptions.AffectsRender));
    public static readonly DependencyProperty SecondaryProperty = DependencyProperty.Register(
        nameof(Secondary), typeof(Brush), typeof(TracePlan), new FrameworkPropertyMetadata(Brushes.Gray, FrameworkPropertyMetadataOptions.AffectsRender));
    public static readonly DependencyProperty ErrorProperty = DependencyProperty.Register(
        nameof(Error), typeof(Brush), typeof(TracePlan), new FrameworkPropertyMetadata(Brushes.Red, FrameworkPropertyMetadataOptions.AffectsRender));

    public TraceSession? Session { get => (TraceSession?)GetValue(SessionProperty); set => SetValue(SessionProperty, value); }
    public SiaPalette? Palette { get => (SiaPalette?)GetValue(PaletteProperty); set => SetValue(PaletteProperty, value); }
    public Brush Accent { get => (Brush)GetValue(AccentProperty); set => SetValue(AccentProperty, value); }
    public Brush Primary { get => (Brush)GetValue(PrimaryProperty); set => SetValue(PrimaryProperty, value); }
    public Brush Secondary { get => (Brush)GetValue(SecondaryProperty); set => SetValue(SecondaryProperty, value); }
    public Brush Error { get => (Brush)GetValue(ErrorProperty); set => SetValue(ErrorProperty, value); }

    /// <summary>Échap sans polygone en cours : la fenêtre ferme le volet (avec confirmation si besoin).</summary>
    public event EventHandler? CloseRequested;

    private const double SnapPixels = 8;      // rayon d'accrochage
    private const double RightAnglePixels = 6; // accrochage léger aux angles droits
    private const double MarkPixels = 10;     // côté du repère d'angle droit
    private const byte FadedAlpha = 0x14;     // autres surfaces en transparence
    private const double GrabPixels = 12;     // rayon de saisie d'un sommet
    private const double VertexSize = 8;
    private const byte PaleAlpha = 0x73;      // ~45 % : la pâleur des surfaces externes en 3D (SceneController.ExternalTint)
    private const byte SpAlpha = 0x40;        // plancher SP : simple fond gris
    private const double Margin = 24;

    private double _scale = 1;                 // px par m
    private Point _origin;                     // m au coin haut gauche
    private Point? _cursor;                    // m
    private Point? _snap;                      // m
    private IReadOnlyList<RightAngleMark> _rightAngles = [];   // repères d'angle droit sous le curseur
    private TraceSelection? _selected;
    private (int Polygon, int Index)? _dragVertex;
    private (int Polygon, int Index)? _dragEdge;
    private int? _dragPolygon;
    private Point _dragStart;                  // m
    private Point? _panFrom;                   // px
    private bool _spaceDown;

    public TracePlan()
    {
        Focusable = true;
        FocusVisualStyle = null;
        ClipToBounds = true;
        Cursor = Cursors.Cross;
        SizeChanged += (_, _) => { if (Session is not null && _scale == 1) Fit(); };
        ToolTipService.SetInitialShowDelay(this, 600);
    }

    private void OnSession(DependencyPropertyChangedEventArgs e)
    {
        if (e.OldValue is TraceSession old) old.PropertyChanged -= OnSessionChanged;
        if (e.NewValue is TraceSession s) s.PropertyChanged += OnSessionChanged;
        _selected = null;
        _scale = 1;
        Fit();
    }

    private void OnSessionChanged(object? sender, System.ComponentModel.PropertyChangedEventArgs e) => InvalidateVisual();

    /// <summary>F : cadre le niveau entier.</summary>
    public void Fit()
    {
        if (Session is not { } s || ActualWidth <= 0 || s.Bounds.IsEmpty) return;
        var b = s.Bounds;
        _scale = Math.Min((ActualWidth - 2 * Margin) / Math.Max(b.Width, 1), (ActualHeight - 2 * Margin) / Math.Max(b.Height, 1));
        _origin = new Point(b.X - (ActualWidth / _scale - b.Width) / 2, b.Bottom + (ActualHeight / _scale - b.Height) / 2);
        InvalidateVisual();
    }

    private Point ToScreen(Point m) => new((m.X - _origin.X) * _scale, (_origin.Y - m.Y) * _scale);
    private Point ToWorld(Point px) => new(px.X / _scale + _origin.X, _origin.Y - px.Y / _scale);

    // ------------------------------------------------------------------ rendu

    protected override void OnRender(DrawingContext dc)
    {
        dc.DrawRectangle(Brushes.Transparent, null, new Rect(0, 0, ActualWidth, ActualHeight));   // reçoit la souris partout
        if (Session is not { } s || Palette is not { } pal) return;

        foreach (var shape in s.Shapes.OrderBy(x => x.Code == "SP" ? 0 : 1))
        {
            // Aplats en transparence sur le fond : pâles en clair comme en sombre (un éclaircissement vers le blanc
            // ferait dominer les planchers sur fond graphite). « Transparence » : les autres surfaces ne gardent que
            // leur contour et un voile, pour lire le tracé et la surface source.
            var c = shape.Code == "SP" ? SiaPalette.Fallback : pal.ColorOf(shape.Code);
            var faded = s.FadeOthers && !shape.IsSource;
            var fill = new SolidColorBrush(Color.FromArgb(faded ? FadedAlpha : shape.Code == "SP" ? SpAlpha : PaleAlpha, c.R, c.G, c.B));
            fill.Freeze();
            // En transparence, les limites restent lisibles : contour neutre, plus marqué pour le plancher SP.
            dc.DrawGeometry(fill, faded ? (shape.Code == "SP" ? Pen(Primary, 1.5) : Pen(Secondary, 1)) : null, Geometry(shape.Paths));
        }
        var below = Pen(Secondary, 1, dashed: true);
        dc.DrawGeometry(null, below, Geometry(s.BelowOutline));
        foreach (var shape in s.Shapes.Where(x => x.IsSource)) dc.DrawGeometry(null, Pen(Primary, 2), Geometry(shape.Paths));

        // Aire comptée (aplat Accent 20 %), puis polygones dessinés (liseré Accent, ou erreur s'ils se recoupent).
        var accent = (Accent as SolidColorBrush)?.Color ?? Colors.SlateBlue;
        var counted = new SolidColorBrush(Color.FromArgb(0x33, accent.R, accent.G, accent.B));
        counted.Freeze();
        dc.DrawGeometry(counted, null, Geometry(s.Counted));
        var edge = Pen(s.IsSelfIntersecting ? Error : Accent, 2);
        for (var k = 0; k < s.Polygons.Count; k++)
        {
            var poly = s.Polygons[k];
            var open = s.IsDrawingOpen && k == s.Polygons.Count - 1;
            var g = new StreamGeometry();
            using (var ctx = g.Open())
            {
                if (poly.Count > 0)
                {
                    ctx.BeginFigure(ToScreen(poly[0]), false, !open);
                    ctx.PolyLineTo(poly.Skip(1).Select(ToScreen).ToList(), true, true);
                    if (open && _cursor is { } cur) ctx.LineTo(ToScreen(_snap ?? cur), true, true);
                }
            }
            g.Freeze();
            dc.DrawGeometry(null, edge, g);
            if (_selected is { IsEdge: true } se && se.Polygon == k && poly.Count >= 2)
                dc.DrawLine(Pen(Accent, 5), ToScreen(poly[se.Index]), ToScreen(poly[(se.Index + 1) % poly.Count]));
            for (var i = 0; i < poly.Count; i++)
            {
                var p = ToScreen(poly[i]);
                var sel = _selected == new TraceSelection(k, i, false) || _dragVertex == (k, i);
                var size = sel ? VertexSize + 4 : VertexSize;
                dc.DrawRectangle(sel ? Accent : Brushes.White, Pen(Accent, 1.5), new Rect(p.X - size / 2, p.Y - size / 2, size, size));
            }
        }
        if (_snap is { } sp)   // losange : point d'accrochage sous le curseur
        {
            var p = ToScreen(sp);
            var d = new StreamGeometry();
            using (var ctx = d.Open())
            {
                ctx.BeginFigure(new Point(p.X, p.Y - 6), false, true);
                ctx.PolyLineTo([new(p.X + 6, p.Y), new(p.X, p.Y + 6), new(p.X - 6, p.Y)], true, true);
            }
            d.Freeze();
            dc.DrawGeometry(null, Pen(Accent, 1.5), d);
        }
        foreach (var mark in _rightAngles) DrawRightAngle(dc, mark);
        DrawScale(dc);
        if (_cursor is { } c2) Text(dc, $"x {c2.X:#,##0.00}   y {c2.Y:#,##0.00}", new Point(ActualWidth - 12, ActualHeight - 22), right: true, mono: true);
    }

    /// <summary>Repère d'angle droit : petit carré à l'angle, côtés le long des deux arêtes.</summary>
    private void DrawRightAngle(DrawingContext dc, RightAngleMark m)
    {
        var len = MarkPixels / _scale;
        var a = ToScreen(m.Corner + m.U * len);
        var b = ToScreen(m.Corner + m.U * len + m.V * len);
        var c = ToScreen(m.Corner + m.V * len);
        var g = new StreamGeometry();
        using (var ctx = g.Open())
        {
            ctx.BeginFigure(a, false, false);
            ctx.PolyLineTo([b, c], true, true);
        }
        g.Freeze();
        dc.DrawGeometry(null, Pen(Accent, 1.5), g);
    }

    private void DrawScale(DrawingContext dc)
    {
        var target = 120 / _scale;   // ~120 px
        var step = new[] { 1, 2, 5, 10, 20, 50, 100, 200 }.Select(v => (double)v).FirstOrDefault(v => v >= target * 0.6, 500);
        var len = step * _scale;
        var y = ActualHeight - 16;
        var pen = Pen(Secondary, 1);
        dc.DrawLine(pen, new Point(16, y), new Point(16 + len, y));
        dc.DrawLine(pen, new Point(16, y - 4), new Point(16, y + 4));
        dc.DrawLine(pen, new Point(16 + len, y - 4), new Point(16 + len, y + 4));
        Text(dc, $"{step:0} m", new Point(16 + len / 2, y - 18), center: true);
    }

    private void Text(DrawingContext dc, string text, Point at, bool right = false, bool center = false, bool mono = false)
    {
        var ft = new FormattedText(text, CultureInfo.CurrentCulture, FlowDirection.LeftToRight,
            new Typeface((FontFamily)FindResource(mono ? "FontMono" : "FontUI"), FontStyles.Normal, FontWeights.Normal, FontStretches.Normal), 12, Secondary,
            VisualTreeHelper.GetDpi(this).PixelsPerDip);
        var x = right ? at.X - ft.Width : center ? at.X - ft.Width / 2 : at.X;
        dc.DrawText(ft, new Point(x, at.Y));
    }

    private StreamGeometry Geometry(PathsD paths)
    {
        var g = new StreamGeometry { FillRule = System.Windows.Media.FillRule.Nonzero };
        using (var ctx = g.Open())
            foreach (var path in paths)
            {
                if (path.Count < 2) continue;
                ctx.BeginFigure(ToScreen(new Point(path[0].x, path[0].y)), true, true);
                ctx.PolyLineTo(path.Skip(1).Select(p => ToScreen(new Point(p.x, p.y))).ToList(), true, true);
            }
        g.Freeze();
        return g;
    }

    private static Pen Pen(Brush b, double w, bool dashed = false)
    {
        var p = new Pen(b, w) { LineJoin = PenLineJoin.Round };
        if (dashed) p.DashStyle = new DashStyle([4, 3], 0);
        p.Freeze();
        return p;
    }

    // ------------------------------------------------------------------ souris

    private Point Constrained(Point m)
    {
        _rightAngles = [];
        if (Session is not { } s) return m;
        Point? snapped = null;
        if ((Keyboard.Modifiers & ModifierKeys.Alt) == 0)
        {
            // Sommet existant d'abord ; sinon angle droit avec le tracé ou arête existante, le plus proche des deux
            // (à l'intersection des deux quand elle est sous le curseur).
            snapped = s.SnapToVertex(m, SnapPixels / _scale);
            if (snapped is null)
            {
                var edge = s.SnapToEdge(m, SnapPixels / _scale);
                var (anchors, corner) = RightAngleAnchors(s);
                var right = s.SnapRightAngle(m, anchors, RightAnglePixels / _scale, corner);
                if (right is { } r && edge is { } e)
                {
                    var onEdge = s.SnapRightAngle(e.At, anchors, RightAnglePixels / _scale, corner);
                    if (onEdge is { } both && DistanceToLine(both.At, e.A, e.B) < 1e-3) right = both;   // angle droit sur l'arête
                    else if ((e.At - m).Length < (r.At - m).Length) right = null;
                }
                if (right is { } ra) { snapped = ra.At; _rightAngles = ra.Marks; }
                else snapped = edge?.At;
            }
        }
        _snap = snapped;
        var p = snapped ?? m;
        if ((Keyboard.Modifiers & ModifierKeys.Shift) != 0 && Anchor() is { } a)   // horizontal ou vertical
            p = Math.Abs(p.X - a.X) >= Math.Abs(p.Y - a.Y) ? new Point(p.X, a.Y) : new Point(a.X, p.Y);
        return p;
    }

    /// <summary>
    /// Droites d'angle droit du geste en cours : en dessinant, au dernier point (prolongement d'équerre) et au premier
    /// (fermeture d'équerre) ; en glissant un sommet, chez ses deux voisins, plus l'angle au sommet lui-même.
    /// </summary>
    private (List<(Point, Point)> Anchors, (Point, Point)? Corner) RightAngleAnchors(TraceSession s)
    {
        var anchors = new List<(Point, Point)>();
        if (_dragVertex is { } v)
        {
            var poly = s.Polygons[v.Polygon];
            var n = poly.Count;
            var open = s.IsDrawingOpen && v.Polygon == s.Polygons.Count - 1;
            if (n < 3) return (anchors, null);
            Point At(int k) => poly[((k % n) + n) % n];
            if (!open || v.Index >= 2) anchors.Add((At(v.Index - 1), At(v.Index - 2)));
            if (!open || v.Index <= n - 3) anchors.Add((At(v.Index + 1), At(v.Index + 2)));
            return (anchors, open && (v.Index == 0 || v.Index == n - 1) ? null : (At(v.Index - 1), At(v.Index + 1)));
        }
        if (s.Mode == TraceMode.Draw && s.IsDrawingOpen && s.Polygons[^1] is { Count: >= 2 } pts)
        {
            anchors.Add((pts[^1], pts[^2]));
            anchors.Add((pts[0], pts[1]));
        }
        return (anchors, null);
    }

    private static double DistanceToLine(Point p, Point a, Point b)
    {
        var ab = b - a;
        return ab.LengthSquared < 1e-12 ? (p - a).Length : Math.Abs(Vector.CrossProduct(ab, p - a)) / ab.Length;
    }

    /// <summary>Point de référence de la contrainte Maj : dernier point posé, ou voisin du sommet glissé.</summary>
    private Point? Anchor()
    {
        if (Session is not { } s) return null;
        if (_dragVertex is { } v)
        {
            var poly = s.Polygons[v.Polygon];
            return poly[(v.Index - 1 + poly.Count) % poly.Count];
        }
        return s.IsDrawingOpen && s.Polygons[^1].Count > 0 ? s.Polygons[^1][^1] : null;
    }

    protected override void OnMouseDown(MouseButtonEventArgs e)
    {
        base.OnMouseDown(e);
        Focus();
        if (Session is not { } s) return;
        var px = e.GetPosition(this);
        if (e.ChangedButton == MouseButton.Middle || (e.ChangedButton == MouseButton.Left && _spaceDown))
        {
            _panFrom = px;
            CaptureMouse();
            return;
        }
        if (e.ChangedButton != MouseButton.Left) return;
        var m = ToWorld(px);
        if (s.Mode == TraceMode.Draw)
        {
            if (e.ClickCount == 2 || s.IsFirstPoint(m, GrabPixels / _scale)) { s.ClosePolygon(); _snap = null; return; }
            s.AddPoint(Constrained(m));
            return;
        }
        if (e.ClickCount == 2 && s.EdgeAt(m, GrabPixels / _scale) is { } edge)
        {
            s.InsertVertex(edge.Polygon, edge.Index, edge.At);
            _selected = new TraceSelection(edge.Polygon, edge.Index + 1, false);
            return;
        }
        if (s.VertexAt(m, GrabPixels / _scale) is { } v)
        {
            s.BeginChange();
            _dragVertex = v;
            _selected = new TraceSelection(v.Polygon, v.Index, false);
            CaptureMouse();
        }
        else if (s.EdgeAt(m, GrabPixels / _scale) is { } ed)   // arête : sélectionnée, et glissée en entier
        {
            s.BeginChange();
            _dragEdge = (ed.Polygon, ed.Index);
            _dragStart = m;
            _selected = new TraceSelection(ed.Polygon, ed.Index, true);
            CaptureMouse();
        }
        else if (s.PolygonAt(m) is { } k)
        {
            s.BeginChange();
            _dragPolygon = k;
            _dragStart = m;
            _selected = null;
            CaptureMouse();
        }
        else _selected = null;
        InvalidateVisual();
    }

    protected override void OnMouseMove(MouseEventArgs e)
    {
        base.OnMouseMove(e);
        if (Session is not { } s) return;
        var px = e.GetPosition(this);
        if (_panFrom is { } from)
        {
            var d = px - from;
            _origin = new Point(_origin.X - d.X / _scale, _origin.Y + d.Y / _scale);
            _panFrom = px;
            InvalidateVisual();
            return;
        }
        var m = ToWorld(px);
        _cursor = m;
        if (_dragVertex is { } v) s.MoveVertex(v.Polygon, v.Index, Constrained(m));
        else if (_dragEdge is { } ed) { s.MoveEdge(ed.Polygon, ed.Index, m - _dragStart); _dragStart = m; _snap = null; }
        else if (_dragPolygon is { } k) { s.MovePolygon(k, m - _dragStart); _dragStart = m; _snap = null; }
        else if (s.Mode == TraceMode.Draw) Constrained(m);
        else { _snap = null; _rightAngles = []; }
        Cursor = _spaceDown || _panFrom is not null ? Cursors.SizeAll
            : s.Mode == TraceMode.Edit && (s.VertexAt(m, GrabPixels / _scale) is not null) ? Cursors.Hand
            : s.Mode == TraceMode.Edit && (s.EdgeAt(m, GrabPixels / _scale) is not null || s.PolygonAt(m) is not null) ? Cursors.SizeAll
            : s.Mode == TraceMode.Draw && s.IsFirstPoint(m, GrabPixels / _scale) ? Cursors.Hand : Cursors.Cross;
        ToolTip = Hover(m);
        InvalidateVisual();
    }

    protected override void OnMouseUp(MouseButtonEventArgs e)
    {
        base.OnMouseUp(e);
        _panFrom = null;
        _dragVertex = null;
        _dragEdge = null;
        _dragPolygon = null;
        _rightAngles = [];
        if (IsMouseCaptured) ReleaseMouseCapture();
        InvalidateVisual();
    }

    protected override void OnMouseLeave(MouseEventArgs e)
    {
        base.OnMouseLeave(e);
        _cursor = null;
        _snap = null;
        InvalidateVisual();
    }

    protected override void OnMouseWheel(MouseWheelEventArgs e)
    {
        base.OnMouseWheel(e);
        var px = e.GetPosition(this);
        var before = ToWorld(px);
        _scale = Math.Clamp(_scale * (e.Delta > 0 ? 1.2 : 1 / 1.2), 0.05, 500);
        var after = ToWorld(px);
        _origin = new Point(_origin.X + before.X - after.X, _origin.Y + before.Y - after.Y);
        InvalidateVisual();
    }

    /// <summary>Infobulle : la surface sous le curseur (code, aire, identifiant).</summary>
    private object? Hover(Point m)
    {
        if (Session is not { } s) return null;
        var hit = s.Shapes.LastOrDefault(x => x.Code != "SP" && x.Paths.Any(p =>
            Clipper.PointInPolygon(new PointD(m.X, m.Y), p) != PointInPolygonResult.IsOutside));
        return hit is null ? null : $"{hit.Code} · {hit.Id}";
    }

    // ------------------------------------------------------------------ clavier

    protected override void OnKeyDown(KeyEventArgs e)
    {
        base.OnKeyDown(e);
        if (Session is not { } s) return;
        var ctrl = (Keyboard.Modifiers & ModifierKeys.Control) != 0;
        var step = (Keyboard.Modifiers & ModifierKeys.Shift) != 0 ? 1.0 : 0.1;
        switch (e.Key)
        {
            case Key.Space: _spaceDown = true; Cursor = Cursors.SizeAll; break;
            case Key.Enter when s.Mode == TraceMode.Draw: s.ClosePolygon(); break;
            case Key.Back when s.Mode == TraceMode.Draw: s.RemoveLastPoint(); break;
            case Key.Delete or Key.Back when s.Mode == TraceMode.Edit && _selected is { IsEdge: false } v:
                s.DeleteVertex(v.Polygon, v.Index);
                _selected = null;
                break;
            case Key.Delete or Key.Back when s.Mode == TraceMode.Edit && _selected is { IsEdge: true } ed:
                s.DeleteEdge(ed.Polygon, ed.Index);   // le contour s'ouvre : on le complète en mode Tracer
                _selected = null;
                break;
            case Key.Z when ctrl: s.Undo(); _selected = null; break;
            case Key.Y when ctrl: s.Redo(); _selected = null; break;
            case Key.F: Fit(); break;
            case Key.Escape:
                if (!s.CancelOpenPolygon()) CloseRequested?.Invoke(this, EventArgs.Empty);
                break;
            case Key.Left or Key.Right or Key.Up or Key.Down when _selected is { } v:
                var d = e.Key switch { Key.Left => new Vector(-step, 0), Key.Right => new Vector(step, 0), Key.Up => new Vector(0, step), _ => new Vector(0, -step) };
                if (!e.IsRepeat) s.BeginChange();
                if (v.IsEdge) s.MoveEdge(v.Polygon, v.Index, d);
                else s.MoveVertex(v.Polygon, v.Index, s.Polygons[v.Polygon][v.Index] + d);
                break;
            default: return;
        }
        e.Handled = true;
        InvalidateVisual();
    }

    protected override void OnKeyUp(KeyEventArgs e)
    {
        base.OnKeyUp(e);
        if (e.Key == Key.Space) { _spaceDown = false; Cursor = Cursors.Cross; }
    }
}
