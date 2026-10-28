using System.IO;
using SiaCheck.Viewer.Models;
using SiaCheck.Viewer.Services;

namespace SiaCheck.Viewer.Tests;

public class AiGenerationTests
{
    [Fact]
    public void Prompt_written_by_the_engine_is_loaded_with_its_output_estimate()
    {
        var dir = Directory.CreateTempSubdirectory("siagen-ia").FullName;
        Directory.CreateDirectory(Path.Combine(dir, "generation"));
        File.WriteAllText(AiGenerationService.PromptPath(dir),
            """{"system": "Tu es…", "user": "Projet : P", "questions": 3, "output_tokens": [870, 2610]}""");
        var p = AiGenerationService.LoadPrompt(dir);
        Assert.Equal(("Tu es…", "Projet : P", 3), (p.System, p.User, p.IssueCount));
        Assert.Equal((870L, 2610L), p.Output);
    }

    [Fact]
    public void Response_and_usage_are_saved_next_to_the_generation_report()
    {
        var dir = Directory.CreateTempSubdirectory("siagen-ia").FullName;
        AiGenerationService.SaveResponse(dir, new AiReviewResponse("<decisions>{}</decisions>", 1000, 500, "end_turn"),
                                         new DateTime(2026, 10, 28, 15, 0, 0));
        Assert.Equal("<decisions>{}</decisions>", File.ReadAllText(AiGenerationService.ResponsePath(dir)));
        var usage = File.ReadAllText(AiGenerationService.UsagePath(dir));
        Assert.Contains("\"cost_usd\": 0.014", usage);   // 1 000 × 4 $ + 500 × 20 $ par million
        Assert.Contains("2026-10-28T15:00:00", usage);
    }

    [Fact]
    public void Missing_prompt_is_a_readable_error()
    {
        var dir = Directory.CreateTempSubdirectory("siagen-ia").FullName;
        var ex = Assert.Throws<AiReviewException>(() => AiGenerationService.LoadPrompt(dir));
        Assert.StartsWith("Prompt de l'analyse IA illisible", ex.Message);
    }
}

public class GenerationStateTests
{
    private static GeneratedSpace Space(string gid, string code, double confidence, string? source = "dictionnaire") =>
        new() { Gid = gid, Name = gid, Nature = "piece", Code = code, Type = code, Confidence = confidence, Source = source };

    private static GenerationDecision Decision(string id, string status, string code, string origin = "ia") =>
        new() { Id = id, Origin = origin, Status = status, Code = code };

    [Fact]
    public void State_counts_what_is_left_to_decide_and_to_apply()
    {
        var report = new GenerationReport { Spaces = [Space("a", "SUP", 0.95), Space("b", "SUS", 0.5), Space("c", "SUS", 0.7),
                                                      Space("d", "SI", 0.7), Space("e", "SUP", 1.0, "ia")] };
        var decisions = new List<GenerationDecision>
        {
            Decision("b", "proposée", "SUT"),     // encore à trancher
            Decision("c", "rejetée", "SI"),       // tranché
            Decision("d", "acceptée", "SUT"),     // tranché, pas encore régénéré
            Decision("e", "acceptée", "SUP"),     // déjà appliqué
        };
        Assert.Equal(new GenerationState(ToDecide: 1, Proposals: 1, ToApply: 1), GenerationState.Of(report, decisions));
    }

    [Fact]
    public void Space_rows_show_the_change_and_follow_the_filters()
    {
        var palette = new SiaCheck.Viewer.Scene.SiaPalette([]);
        var proposed = new ViewModels.SpaceItem(Space("b", "SUS", 0.5), Decision("b", "proposée", "SUT"), palette);
        var waiting = new ViewModels.SpaceItem(Space("d", "SI", 0.7), Decision("d", "acceptée", "SUT", "manuel"), palette);
        var sure = new ViewModels.SpaceItem(Space("a", "SUP", 0.95), null, palette);
        Assert.True(proposed is { HasChange: true, TargetCode: "SUT", IsOpenProposal: true, Origin: "✦ IA" });
        Assert.True(waiting is { IsWaiting: true, Origin: "manuel" });
        Assert.Equal([true, false, false], new[] { proposed, waiting, sure }.Select(s => s.Matches("todo")));
        Assert.Equal([true, false, false], new[] { proposed, waiting, sure }.Select(s => s.Matches("ia")));
        Assert.Equal([false, true, false], new[] { proposed, waiting, sure }.Select(s => s.Matches("done")));
    }
}
