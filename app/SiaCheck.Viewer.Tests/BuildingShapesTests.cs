using SiaCheck.Viewer.Services;
using Xunit;

namespace SiaCheck.Viewer.Tests;

/// <summary>Forme des bâtiments (partie 5) : même texte du MDP que le moteur (src/sia_check/formes.py).</summary>
public class BuildingShapesTests
{
    [Fact]
    public void Encode_and_decode_match_the_engine_format()
    {
        Assert.Equal("Rectangle compact", BuildingShapes.Encode(new Dictionary<string, string> { ["A"] = "rectangle compact" }));
        var two = BuildingShapes.Decode("B : carre ; A : Rectangle compact ; C : inconnue");
        Assert.Equal(2, two.Count);
        Assert.Equal("Carré", two["B"]);
        Assert.Equal("A : Rectangle compact ; B : Carré", BuildingShapes.Encode(two));
        Assert.Equal("Îlot de bâtiments : Carré, Rectangle compact", BuildingShapes.Label(two));
        Assert.Equal("En L", BuildingShapes.Label(BuildingShapes.Decode("En L")));
    }

    [Fact]
    public void Same_ignores_order_and_a_lone_building_name()
    {
        Assert.True(BuildingShapes.Same("A : En L ; B : Barre", "B : Barre ; A : En L"));
        Assert.True(BuildingShapes.Same("En L", "A : En L"));
        Assert.False(BuildingShapes.Same("A : En L ; B : Barre", "A : En L ; B : Carré"));
        Assert.False(BuildingShapes.Same("", "Barre"));
    }

    [Fact]
    public void ParseShapes_reads_review_block_and_engine_file_and_drops_unknown_shapes()
    {
        var review = AiReviewParser.ParseShapes("""{"A": {"forme": "barre", "raison": "…"}, "B": {"forme": "Pyramide"}}""");
        Assert.Equal(new Dictionary<string, string> { ["A"] = "Barre" }, review);
        var file = AiReviewParser.ParseShapes("""{"format": "sia-check-formes-ia", "version": 1, "formes": {"1": {"forme": "En U"}}}""");
        Assert.Equal("En U", file["1"]);
        Assert.Empty(AiReviewParser.ParseShapes("pas du json"));
        Assert.Empty(AiReviewParser.ParseShapes(null));
    }
}
