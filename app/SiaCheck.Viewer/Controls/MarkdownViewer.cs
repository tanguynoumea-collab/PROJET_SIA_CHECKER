using System.Text.RegularExpressions;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Documents;
using System.Windows.Media;

namespace SiaCheck.Viewer.Controls;

/// <summary>
/// Rendu du rapport de revue IA : le sous-ensemble markdown des rapports (titres, paragraphes, listes,
/// citations, tableaux, filets, gras, italique, code). Couleurs et polices tirées des tokens, donc du thème.
/// </summary>
public sealed partial class MarkdownViewer : FlowDocumentScrollViewer
{
    public static readonly DependencyProperty MarkdownProperty = DependencyProperty.Register(
        nameof(Markdown), typeof(string), typeof(MarkdownViewer),
        new PropertyMetadata(null, (d, e) => ((MarkdownViewer)d).Document = Render((string?)e.NewValue)));

    public string? Markdown { get => (string?)GetValue(MarkdownProperty); set => SetValue(MarkdownProperty, value); }

    public MarkdownViewer()
    {
        VerticalScrollBarVisibility = ScrollBarVisibility.Auto;
        IsToolBarVisible = false;
        Focusable = true;
    }

    [GeneratedRegex(@"^(#{1,4})\s+(.*)$")] private static partial Regex Heading();
    [GeneratedRegex(@"^\s*([-*]|\d+\.)\s+(.*)$")] private static partial Regex ListItem();
    [GeneratedRegex(@"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")] private static partial Regex TableRule();
    [GeneratedRegex(@"(\*\*[^*]+\*\*|`[^`]+`|(?<![\w*])\*[^*\s][^*]*\*(?![\w*]))")] private static partial Regex Inline();

    public static FlowDocument Render(string? markdown)
    {
        var doc = new FlowDocument { PagePadding = new Thickness(24, 16, 24, 24), TextAlignment = TextAlignment.Left };
        doc.SetResourceReference(FlowDocument.FontFamilyProperty, "FontUI");
        doc.SetResourceReference(FlowDocument.FontSizeProperty, "FontSizeBody");
        doc.SetResourceReference(FlowDocument.ForegroundProperty, "BrushTextPrimary");
        doc.SetResourceReference(FlowDocument.BackgroundProperty, "BrushSurface");
        if (string.IsNullOrEmpty(markdown)) return doc;

        var lines = markdown.Replace("\r\n", "\n").Split('\n');
        for (var i = 0; i < lines.Length;)
        {
            var line = lines[i];
            if (string.IsNullOrWhiteSpace(line)) { i++; continue; }
            if (Heading().Match(line) is { Success: true } h)
            {
                doc.Blocks.Add(HeadingBlock(h.Groups[1].Length, h.Groups[2].Value));
                i++;
            }
            else if (line.Trim() is "---" or "***")
            {
                var rule = new Paragraph { Margin = new Thickness(0, 12, 0, 12), FontSize = 1, BorderThickness = new Thickness(0, 1, 0, 0) };
                rule.SetResourceReference(Block.BorderBrushProperty, "BrushDivider");
                doc.Blocks.Add(rule);
                i++;
            }
            else if (line.TrimStart().StartsWith('>'))
            {
                var quote = new Section { Margin = new Thickness(0, 4, 0, 8), Padding = new Thickness(12, 2, 0, 2), BorderThickness = new Thickness(2, 0, 0, 0) };
                quote.SetResourceReference(Block.BorderBrushProperty, "BrushDivider");
                quote.SetResourceReference(Block.ForegroundProperty, "BrushTextSecondary");
                for (; i < lines.Length && lines[i].TrimStart().StartsWith('>'); i++)
                    quote.Blocks.Add(Para(lines[i].TrimStart()[1..].Trim(), new Thickness(0, 0, 0, 2)));
                doc.Blocks.Add(quote);
            }
            else if (line.TrimStart().StartsWith('|') && i + 1 < lines.Length && TableRule().IsMatch(lines[i + 1]))
            {
                var rows = new List<string> { line };
                var rule = lines[i + 1];
                for (i += 2; i < lines.Length && lines[i].TrimStart().StartsWith('|'); i++) rows.Add(lines[i]);
                doc.Blocks.Add(TableBlock(rows, rule));
            }
            else if (ListItem().IsMatch(line))
            {
                var ordered = char.IsDigit(ListItem().Match(line).Groups[1].Value[0]);
                var list = new List { MarkerStyle = ordered ? TextMarkerStyle.Decimal : TextMarkerStyle.Disc, Margin = new Thickness(0, 0, 0, 8), Padding = new Thickness(20, 0, 0, 0) };
                for (; i < lines.Length && ListItem().Match(lines[i]) is { Success: true } m; i++)
                    list.ListItems.Add(new ListItem(Para(m.Groups[2].Value, new Thickness(0, 0, 0, 2))));
                doc.Blocks.Add(list);
            }
            else
            {
                var text = new List<string>();
                for (; i < lines.Length && !string.IsNullOrWhiteSpace(lines[i]) && !StartsBlock(lines, i); i++) text.Add(lines[i].Trim());
                if (text.Count == 0) { text.Add(line.Trim()); i++; }
                doc.Blocks.Add(Para(string.Join(" ", text), new Thickness(0, 0, 0, 8)));
            }
        }
        return doc;
    }

    private static bool StartsBlock(string[] lines, int i)
    {
        var l = lines[i];
        return Heading().IsMatch(l) || ListItem().IsMatch(l) || l.TrimStart().StartsWith('>') || l.Trim() is "---" or "***"
               || (l.TrimStart().StartsWith('|') && i + 1 < lines.Length && TableRule().IsMatch(lines[i + 1]));
    }

    private static Paragraph HeadingBlock(int level, string text)
    {
        var p = Para(text, new Thickness(0, level == 1 ? 0 : 16, 0, 6));
        p.FontWeight = FontWeights.SemiBold;
        p.SetResourceReference(TextElement.FontFamilyProperty, "FontUISemibold");
        p.SetResourceReference(TextElement.FontSizeProperty, level switch { 1 => "FontSizeTitle", 2 => "FontSizeSubtitle", _ => "FontSizeBody" });
        return p;
    }

    private static Paragraph Para(string text, Thickness margin)
    {
        var p = new Paragraph { Margin = margin };
        AddInlines(p.Inlines, text);
        return p;
    }

    private static void AddInlines(InlineCollection target, string text)
    {
        var pos = 0;
        foreach (Match m in Inline().Matches(text))
        {
            if (m.Index > pos) target.Add(new Run(text[pos..m.Index]));
            var v = m.Value;
            if (v.StartsWith("**")) target.Add(new Bold(new Run(v[2..^2])));
            else if (v.StartsWith('`'))
            {
                var code = new Run(v[1..^1]);
                code.SetResourceReference(TextElement.FontFamilyProperty, "FontMono");
                code.SetResourceReference(TextElement.FontSizeProperty, "FontSizeMono");
                target.Add(code);
            }
            else target.Add(new Italic(new Run(v[1..^1])));
            pos = m.Index + m.Length;
        }
        if (pos < text.Length) target.Add(new Run(text[pos..]));
    }

    private static string[] Cells(string row)
    {
        var r = row.Trim();
        if (r.StartsWith('|')) r = r[1..];
        if (r.EndsWith('|')) r = r[..^1];
        return r.Split('|').Select(c => c.Trim()).ToArray();
    }

    private static Table TableBlock(List<string> rows, string rule)
    {
        var align = Cells(rule).Select(c => c.EndsWith(':') ? TextAlignment.Right : TextAlignment.Left).ToArray();
        var cols = rows.Max(r => Cells(r).Length);
        var table = new Table { CellSpacing = 0, Margin = new Thickness(0, 4, 0, 12), BorderThickness = new Thickness(0, 0, 0, 1) };
        table.SetResourceReference(Block.BorderBrushProperty, "BrushDivider");
        for (var c = 0; c < cols; c++) table.Columns.Add(new TableColumn { Width = GridLength.Auto });
        var group = new TableRowGroup();
        table.RowGroups.Add(group);
        for (var r = 0; r < rows.Count; r++)
        {
            var row = new TableRow();
            if (r == 0)
            {
                row.SetResourceReference(TextElement.FontFamilyProperty, "FontUISemibold");
                row.FontWeight = FontWeights.SemiBold;
                row.SetResourceReference(TableRow.BackgroundProperty, "BrushSurfaceRaised");
            }
            var cells = Cells(rows[r]);
            for (var c = 0; c < cols; c++)
            {
                var p = Para(c < cells.Length ? cells[c] : "", new Thickness(0));
                p.TextAlignment = c < align.Length ? align[c] : TextAlignment.Left;
                if (p.TextAlignment == TextAlignment.Right) Typography.SetNumeralAlignment(p, FontNumeralAlignment.Tabular);
                var cell = new TableCell(p) { Padding = new Thickness(8, 3, 8, 3), BorderThickness = new Thickness(0, 1, 0, 0) };
                cell.SetResourceReference(TableCell.BorderBrushProperty, "BrushDivider");
                row.Cells.Add(cell);
            }
            group.Rows.Add(row);
        }
        return table;
    }
}
