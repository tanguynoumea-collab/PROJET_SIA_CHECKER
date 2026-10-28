using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace SiaCheck.Viewer.Services;

/// <summary>
/// Analyse IA d'un projet généré depuis l'IFC (V4, phase 24). Le moteur Python prépare les questions et le prompt
/// (<c>sia-check --questions-ia</c>, generation/prompt-ia.json) puis lit la réponse (<c>--reponse-ia</c>) et l'ajoute
/// au journal des décisions comme propositions. L'application ne fait que l'appel : estimation du coût, accord,
/// requête avec la clé chiffrée DPAPI, réponse brute enregistrée (generation/reponse-ia.txt).
/// </summary>
public sealed class AiGenerationService(AnalysisService engine)
{
    public static string PromptPath(string dir) => Path.Combine(dir, "generation", "prompt-ia.json");
    public static string ResponsePath(string dir) => Path.Combine(dir, "generation", "reponse-ia.txt");
    public static string UsagePath(string dir) => Path.Combine(dir, "generation", "reponse-ia.json");
    public static string SummaryPath(string dir) => Path.Combine(dir, "generation", "synthese-ia.md");

    /// <summary>Prompt écrit par le moteur : system, user, nombre de questions, sortie attendue en jetons.</summary>
    public static AiReviewPrompt LoadPrompt(string dir)
    {
        JsonObject doc;
        try { doc = JsonNode.Parse(File.ReadAllText(PromptPath(dir))) as JsonObject ?? throw new JsonException("objet attendu"); }
        catch (Exception ex) when (ex is IOException or JsonException)
        {
            throw new AiReviewException($"Prompt de l'analyse IA illisible : {ex.Message}", ex);
        }
        var output = doc["output_tokens"]?.AsArray();
        return new AiReviewPrompt
        {
            System = (string?)doc["system"] ?? throw new AiReviewException("Prompt de l'analyse IA sans « system »."),
            User = (string?)doc["user"] ?? throw new AiReviewException("Prompt de l'analyse IA sans « user »."),
            IssueCount = (int?)doc["questions"] ?? 0,
            Output = output is [var lo, var hi] ? ((long)lo!, (long)hi!) : null,
        };
    }

    /// <summary>Questions et prompt du projet généré, préparés par le moteur.</summary>
    public async Task<AiReviewPrompt> PrepareAsync(string dir, CancellationToken ct)
    {
        var run = await engine.QuestionsIaAsync(dir, ct);
        if (!run.Succeeded) throw new AiReviewException(run.ErrorMessage ?? "Préparation de l'analyse IA impossible.");
        return LoadPrompt(dir);
    }

    /// <summary>Réponse brute et consommation (jetons, coût, modèle) à côté du rapport de génération.</summary>
    public static void SaveResponse(string dir, AiReviewResponse response, DateTime when)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(ResponsePath(dir))!);
        File.WriteAllText(ResponsePath(dir), response.Text);
        var usage = new JsonObject
        {
            ["model"] = AiPricing.Model, ["date"] = when.ToString("s"),
            ["input_tokens"] = response.InputTokens, ["output_tokens"] = response.OutputTokens,
            ["cost_usd"] = Math.Round(response.CostUsd, 4), ["stop_reason"] = response.StopReason,
        };
        File.WriteAllText(UsagePath(dir), usage.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
    }

    /// <summary>Réponse enregistrée -> propositions du journal (moteur). Renvoie la ligne de bilan du moteur.</summary>
    public async Task<string> RecordAsync(string dir, CancellationToken ct)
    {
        var run = await engine.ReponseIaAsync(dir, ct);
        if (!run.Succeeded) throw new AiReviewException(run.ErrorMessage ?? "Réponse de l'analyse IA inexploitable.");
        return run.Log.Split('\n').Select(l => l.Trim()).LastOrDefault(l => l.Contains("analyse IA")) ?? "";
    }
}
