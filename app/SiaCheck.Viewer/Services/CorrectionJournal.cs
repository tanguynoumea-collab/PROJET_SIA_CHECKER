using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;
using SiaCheck.Viewer.Models;

namespace SiaCheck.Viewer.Services;

/// <summary>Fichier du journal : format de src/sia_check/corrections.py, plus l'état de la dernière analyse.</summary>
public sealed class CorrectionJournalData
{
    [JsonPropertyName("version")] public int Version { get; set; } = 1;
    [JsonPropertyName("projet")] public string? Project { get; set; }
    /// <summary>Décisions de l'utilisateur : une entrée complète par correction acceptée, rejetée ou modifiée.</summary>
    [JsonPropertyName("corrections")] public List<Correction> Corrections { get; set; } = [];
    /// <summary>Signature de chaque décision au moment de la dernière analyse (ce que le moteur a appliqué).</summary>
    [JsonPropertyName("analysee")] public Dictionary<string, string> Analysed { get; set; } = [];
}

/// <summary>
/// Décisions sur les corrections d'un projet, persistées par <c>id</c> d'une analyse à l'autre (plan,
/// Évolution 2.0). Le moteur propose ; le journal garde ce que l'utilisateur a décidé, qui prime toujours :
/// une nouvelle proposition de même <c>id</c> reprend le statut du journal, et une correction modifiée à la
/// main (origine « manuel ») remplace la proposition. Le fichier est passé tel quel à
/// <c>sia-check --corrections</c>, qui n'applique que les corrections « acceptée ».
/// </summary>
public sealed class CorrectionJournal
{
    private readonly string _path;
    private readonly CorrectionJournalData _data;

    private CorrectionJournal(string path, CorrectionJournalData data) => (_path, _data) = (path, data);

    public string Path => _path;

    public static CorrectionJournal Open(string path, string? project)
    {
        var data = JsonFile.ReadOrDefault<CorrectionJournalData>(path);
        data.Project ??= project;
        return new CorrectionJournal(path, data);
    }

    public IReadOnlyList<Correction> Decisions => _data.Corrections;
    public bool HasDecisions => _data.Corrections.Count > 0;
    public Correction? Get(string id) => _data.Corrections.FirstOrDefault(c => c.Id == id);

    /// <summary>La proposition telle que l'utilisateur la voit : décision du journal par-dessus.</summary>
    public Correction Overlay(Correction proposal)
    {
        if (Get(proposal.Id) is not { } d) return proposal;
        if (d.Origin == "manuel") return d.Clone();
        var c = proposal.Clone();
        c.Status = d.Status;
        return c;
    }

    /// <summary>Enregistre une décision (statut, ou correction modifiée) ; « proposée » non modifiée efface l'entrée.</summary>
    public void Decide(Correction c)
    {
        _data.Corrections.RemoveAll(x => x.Id == c.Id);
        if (c.Status != Correction.Proposed || c.Origin == "manuel") _data.Corrections.Add(c.Clone());
        Save();
    }

    /// <summary>Décisions qui ne correspondent plus à aucune proposition (cible disparue d'une livraison à l'autre).</summary>
    public IReadOnlyList<Correction> Orphans(IEnumerable<string> proposalIds)
    {
        var known = proposalIds.ToHashSet();
        return _data.Corrections.Where(c => !known.Contains(c.Id)).ToList();
    }

    /// <summary>Décisions pas encore appliquées par une analyse (nouvelles, changées ou retirées depuis).</summary>
    public int PendingCount
    {
        get
        {
            var now = _data.Corrections.Where(Effective).ToDictionary(c => c.Id, c => c.Signature);
            return now.Count(kv => !_data.Analysed.TryGetValue(kv.Key, out var s) || s != kv.Value)
                   + _data.Analysed.Keys.Count(id => !now.ContainsKey(id));
        }
    }

    /// <summary>Après une analyse réussie lancée avec ce journal : son état devient l'état appliqué.</summary>
    public void MarkAnalysed()
    {
        _data.Analysed = _data.Corrections.Where(Effective).ToDictionary(c => c.Id, c => c.Signature);
        Save();
    }

    /// <summary>Seules les corrections acceptées changent le résultat du moteur.</summary>
    private static bool Effective(Correction c) => c.Status == Correction.Accepted;

    private void Save() => JsonFile.Write(_path, _data);
}
