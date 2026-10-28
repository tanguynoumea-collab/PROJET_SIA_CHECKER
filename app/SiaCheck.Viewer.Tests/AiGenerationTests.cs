using System.IO;
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
