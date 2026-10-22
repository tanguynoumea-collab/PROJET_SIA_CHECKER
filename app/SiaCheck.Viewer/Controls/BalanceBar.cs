using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using SiaCheck.Viewer.Scene;
using SiaCheck.Viewer.ViewModels;

namespace SiaCheck.Viewer.Controls;

/// <summary>
/// Barre de sommation d'un niveau (plan de design §6) :
/// longueur = SP, remplie par SUP, SUS, SD, SI aux couleurs SIA ; ce qui n'est pas couvert
/// reste vide avec un simple contour (le résidu, rendu visible). Dessous, plus fine,
/// la SEP hachurée avec SEU et SED. Si les sous-catégories dépassent la SP (R4), le surplus
/// déborde de la barre, contouré dans la couleur d'erreur.
///
/// Au survol, une infobulle décrit le segment sous la souris : catégorie SIA (nom, chiffre,
/// définition), aire et part de la SP — ou le résidu non classé.
///
/// Avant / après (plan, Évolution 2.0) : la barre montre toujours l'état corrigé ; ce que les corrections
/// ont retiré (SP ou SEP plus courtes qu'avant) prolonge la barre en contour pointillé.
/// </summary>
public sealed class BalanceBar : FrameworkElement
{
    public static readonly DependencyProperty RowProperty = DependencyProperty.Register(
        nameof(Row), typeof(BalanceRow), typeof(BalanceBar), new FrameworkPropertyMetadata(null, FrameworkPropertyMetadataOptions.AffectsRender));

    public static readonly DependencyProperty PaletteProperty = DependencyProperty.Register(
        nameof(Palette), typeof(SiaPalette), typeof(BalanceBar), new FrameworkPropertyMetadata(null, FrameworkPropertyMetadataOptions.AffectsRender));

    public static readonly DependencyProperty OutlineProperty = DependencyProperty.Register(
        nameof(Outline), typeof(Brush), typeof(BalanceBar), new FrameworkPropertyMetadata(Brushes.Gray, FrameworkPropertyMetadataOptions.AffectsRender));

    public static readonly DependencyProperty ErrorProperty = DependencyProperty.Register(
        nameof(Error), typeof(Brush), typeof(BalanceBar), new FrameworkPropertyMetadata(Brushes.Red, FrameworkPropertyMetadataOptions.AffectsRender));

    public BalanceRow? Row { get => (BalanceRow?)GetValue(RowProperty); set => SetValue(RowProperty, value); }
    public SiaPalette? Palette { get => (SiaPalette?)GetValue(PaletteProperty); set => SetValue(PaletteProperty, value); }
    /// <summary>Contour du résidu (TextSecondary).</summary>
    public Brush Outline { get => (Brush)GetValue(OutlineProperty); set => SetValue(OutlineProperty, value); }
    /// <summary>Contour du dépassement R4 (VerdictError).</summary>
    public Brush Error { get => (Brush)GetValue(ErrorProperty); set => SetValue(ErrorProperty, value); }

    private const double FloorShare = 0.62;   // part de la hauteur pour la barre SP
    private const double Gap = 2;

    private enum Kind { Part, Residual, Excess, External, ExternalResidual, Removed }
    private sealed record Segment(Rect Rect, Kind Kind, string Code, double Area);

    private readonly ToolTip _tip = new() { Placement = System.Windows.Controls.Primitives.PlacementMode.Mouse };
    private Segment? _hovered;

    public BalanceBar()
    {
        ToolTip = _tip;
        ToolTipService.SetInitialShowDelay(this, 150);
        ToolTipService.SetShowDuration(this, 30000);
        ToolTipOpening += (_, e) => { if (_hovered is null) e.Handled = true; };
    }

    private List<Segment> Layout()
    {
        var segs = new List<Segment>();
        if (Row is not { } row || ActualWidth <= 0) return segs;
        var w = ActualWidth;
        var h = ActualHeight;
        double X(double m2) => Math.Max(0, m2 / row.Scale * w);

        var floorH = (row.Sep > 0 || row.SepBefore > 0) && row.HasFloor ? h * FloorShare : h;
        if (row.HasFloor)
        {
            double x = 0, covered = 0;
            foreach (var code in BalanceRow.FloorParts)
            {
                var area = row.Source.Value(code);
                var len = X(area);
                if (len <= 0) continue;
                segs.Add(new Segment(new Rect(x, 0, len, floorH), Kind.Part, code, area));
                x += len;
                covered += area;
            }
            var sp = X(row.Sp);
            if (x < sp - 0.5) segs.Add(new Segment(new Rect(x, 0, sp - x, floorH), Kind.Residual, "SP", row.Sp - covered));
            else if (x > sp + 0.5) segs.Add(new Segment(new Rect(sp, 0, x - sp, floorH), Kind.Excess, "SP", covered - row.Sp));
            if (X(row.SpBefore) > sp + 0.5)
                segs.Add(new Segment(new Rect(sp, 0, X(row.SpBefore) - sp, floorH), Kind.Removed, "SP", row.SpBefore - row.Sp));
        }
        if (row.Sep > 0 || row.SepBefore > 0)
        {
            var y = row.HasFloor ? floorH + Gap : 0;
            var sepH = h - y;
            double x = 0, covered = 0;
            foreach (var code in BalanceRow.ExternalParts)
            {
                var area = row.Source.Value(code);
                var len = X(area);
                if (len <= 0) continue;
                segs.Add(new Segment(new Rect(x, y, len, sepH), Kind.Part, code, area));
                x += len;
                covered += area;
            }
            var sep = X(row.Sep);
            if (x < sep - 0.5) segs.Add(new Segment(new Rect(x, y, sep - x, sepH), Kind.ExternalResidual, "SEP", row.Sep - covered));
            if (X(row.SepBefore) > sep + 0.5)
                segs.Add(new Segment(new Rect(sep, y, X(row.SepBefore) - sep, sepH), Kind.Removed, "SEP", row.SepBefore - row.Sep));
        }
        return segs;
    }

    protected override void OnRender(DrawingContext dc)
    {
        if (Row is not { } row || Palette is not { } pal) return;
        var pen = new Pen(Outline, 1);
        pen.Freeze();
        // Zone de survol : sans fond, une FrameworkElement ne reçoit pas la souris hors des segments.
        dc.DrawRectangle(Brushes.Transparent, null, new Rect(0, 0, ActualWidth, ActualHeight));
        foreach (var s in Layout())
            switch (s.Kind)
            {
                case Kind.Part:
                    dc.DrawRectangle(BalanceRow.ExternalParts.Contains(s.Code) ? new SolidColorBrush(pal.ColorOf(s.Code)) : pal.BrushOf(s.Code),
                                     null, s.Rect);
                    break;
                case Kind.Residual:
                    dc.DrawRectangle(null, pen, Inset(s.Rect, 0.5));
                    break;
                case Kind.Excess:
                    var err = new Pen(Error, 1.5);
                    err.Freeze();
                    dc.DrawRectangle(null, err, Inset(s.Rect, 0.75));
                    break;
                case Kind.ExternalResidual:
                    dc.DrawRectangle(pal.BrushOf("SEP"), null, s.Rect);
                    break;
                case Kind.Removed:
                    var dash = new Pen(Outline, 1) { DashStyle = new DashStyle([2, 2], 0) };
                    dash.Freeze();
                    dc.DrawRectangle(null, dash, Inset(s.Rect, 0.5));
                    break;
            }
        if (row.HasFloor)   // repère de fin de SP, toujours visible : la longueur de référence du niveau
        {
            var sp = Math.Max(0, row.Sp / row.Scale * ActualWidth);
            var floorH = row.Sep > 0 || row.SepBefore > 0 ? ActualHeight * FloorShare : ActualHeight;
            dc.DrawLine(pen, new Point(sp - 0.5, 0), new Point(sp - 0.5, floorH));
        }
    }

    private static Rect Inset(Rect r, double d) =>
        new(r.X + d, r.Y + d, Math.Max(0, r.Width - 2 * d), Math.Max(0, r.Height - 2 * d));

    protected override void OnMouseMove(MouseEventArgs e)
    {
        base.OnMouseMove(e);
        var p = e.GetPosition(this);
        var seg = Layout().FirstOrDefault(s => s.Rect.Contains(p));
        if (seg == _hovered) return;
        _hovered = seg;
        _tip.Content = seg is null ? null : Describe(seg);
        _tip.IsOpen = seg is not null && IsMouseOver;
    }

    protected override void OnMouseLeave(MouseEventArgs e)
    {
        base.OnMouseLeave(e);
        _hovered = null;
        _tip.IsOpen = false;
    }

    private object Describe(Segment s)
    {
        var row = Row!;
        var share = row.Sp > 0 ? $" · {100 * s.Area / row.Sp:0.0} % de la SP" : "";
        var (title, def) = s.Kind switch
        {
            Kind.Residual => ($"Non classé · {row.Building}·{row.Level}",
                              "Part de la SP rattachée à aucune sous-catégorie (règle R1). Jusqu'à ~20 % : en général la surface "
                              + "de construction (murs, cloisons), non fournie par Treegram. Au-delà : espaces non classés."),
            Kind.Excess => ($"Dépassement · {row.Building}·{row.Level}",
                            "Les sous-catégories dépassent la SP (règle R4) : surface comptée deux fois ou SP incomplète."),
            Kind.ExternalResidual => ($"SEP non classée · {row.Building}·{row.Level}",
                                      "SEP sans SEU/SED (règle R3) : balcons ou terrasses non créés, abords (A1) ou toiture (A2)."),
            Kind.Removed => ($"Retiré par les corrections · {s.Code} {row.Building}·{row.Level}",
                             "Ce que les corrections appliquées ont exclu ou découpé (onglet Sujets). La barre pleine est l'état corrigé."),
            _ => Palette!.Describe(s.Code),
        };
        var panel = new StackPanel { MaxWidth = 340 };
        panel.Children.Add(new TextBlock { Text = title, FontWeight = FontWeights.SemiBold, TextWrapping = TextWrapping.Wrap });
        panel.Children.Add(new TextBlock
        {
            Text = $"{s.Area:#,##0.00} m²" + (s.Kind is Kind.External or Kind.ExternalResidual or Kind.Removed
                                                   || BalanceRow.ExternalParts.Contains(s.Code) ? "" : share),
            Margin = new Thickness(0, 2, 0, 0),
        });
        if (def is not null)
            panel.Children.Add(new TextBlock { Text = def, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 6, 0, 0), Opacity = 0.8 });
        return panel;
    }
}
