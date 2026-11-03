using System.Globalization;
using System.Windows;
using System.Windows.Data;

namespace SiaCheck.Viewer.Controls;

/// <summary>true → Visible ; « Invert » pour l'inverse. Accepte bool, null (= false) et chaîne vide (= false).</summary>
public sealed class VisibleWhenConverter : IValueConverter
{
    public bool Invert { get; set; }
    /// <summary>Visibilité quand la condition est fausse : Hidden garde la place (boutons alignés d'une ligne à l'autre).</summary>
    public Visibility Off { get; set; } = Visibility.Collapsed;

    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
    {
        var on = value switch
        {
            bool b => b,
            string s => s.Length > 0,
            int n => n > 0,
            null => false,
            _ => true,
        };
        return on ^ Invert ? Visibility.Visible : Off;
    }

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        throw new NotSupportedException();
}

/// <summary>Valeur == paramètre (pour boutons radio liés à une énumération ou à une chaîne).</summary>
public sealed class EqualsConverter : IValueConverter
{
    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        string.Equals(value?.ToString(), parameter?.ToString(), StringComparison.Ordinal);

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        value is true && parameter is not null
            ? targetType.IsEnum ? Enum.Parse(targetType, parameter.ToString()!) : parameter
            : Binding.DoNothing;
}

/// <summary>m² au format suisse (espace fine comme séparateur de milliers), vide si null.</summary>
public sealed class AreaConverter : IValueConverter
{
    private static readonly NumberFormatInfo Format = new() { NumberGroupSeparator = " ", NumberDecimalSeparator = "," };

    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        value switch
        {
            double d when parameter as string == "pct" => d.ToString("0.0", Format) + " %",
            double d => d.ToString("#,##0.00", Format),
            int n => n.ToString("#,##0", Format),
            _ => "",
        };

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        throw new NotSupportedException();
}

/// <summary>Négation d'un booléen, dans les deux sens (onglets en RadioButton liés à un seul booléen).</summary>
public sealed class NotConverter : IValueConverter
{
    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture) => value is not true;
    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) => value is not true;
}
