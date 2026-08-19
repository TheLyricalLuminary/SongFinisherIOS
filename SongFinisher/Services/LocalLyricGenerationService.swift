import Foundation

/// A fully local, offline lyric generator. This is the zero-configuration default —
/// no network access, no API key, no account.
///
/// It picks a mood (from the *style* first, falling back to the theme prompt),
/// pulls imagery out of the prompt, and selects from hand-written lines using
/// `ProsodyAnalyzer` so the user's craft settings genuinely apply:
///
/// - **Rhyme scheme** works because the line bank is organized into *rhyme
///   families* — groups of lines that rhyme with one another. Filling "AABB"
///   means drawing two lines from one family and two from another.
/// - **Rhyme type** decides which pools can be drawn from: end rhymes use the
///   families as written, near/slant additionally merges families that share a
///   vowel sound, and internal rhyme biases selection toward lines that carry a
///   rhyme inside them.
/// - **Syllable target** (after meter/tempo adjustment) ranks lines by how close
///   they sit to the requested length.
///
/// Because the bank is finite, an exotic combination can still fall short; when
/// a family can't satisfy a group, selection degrades to the best-scoring
/// distinct lines rather than failing.
struct LocalLyricGenerationService: LyricGenerationService {

    func generateLyrics(_ request: LyricGenerationRequest) async throws -> GeneratedLyrics {
        let prompt = request.trimmedPrompt
        guard !prompt.isEmpty else { throw LyricGenerationError.emptyPrompt }

        let settings = request.settings
        let banned = request.bannedWords
        let tone = ToneClassifier.detect(style: settings.trimmedStyle, prompt: prompt)
        let extracted = ImageryExtractor.extract(from: prompt, tone: tone, excluding: banned)
        let images = extracted.isEmpty ? (LineBank.fallbackImagery[tone] ?? ["the quiet"]) : extracted
        let bank = LineBank.banks[tone] ?? LineBank.banks[.bittersweet]!

        let target = settings.effectiveSyllableTarget
        let types = settings.effectiveRhymeTypes
        let pattern = settings.rhymeScheme.pattern

        var usedLines = Set<String>()
        let verse1 = selectStanza(families: bank.verse, images: images, banned: banned,
                                  lineCount: 4, pattern: pattern, target: target, types: types,
                                  usedLines: &usedLines)
        let verse2 = selectStanza(families: bank.verse, images: images, banned: banned,
                                  lineCount: 4, pattern: pattern, target: target, types: types,
                                  usedLines: &usedLines)

        var usedChorusLines = Set<String>()
        let chorus = selectStanza(families: bank.chorus, images: images, banned: banned,
                                  lineCount: 4, pattern: pattern, target: target, types: types,
                                  usedLines: &usedChorusLines)

        var usedBridgeLines = Set<String>()
        let bridge = selectStanza(families: bank.bridge, images: images, banned: banned,
                                  lineCount: 3, pattern: Array(pattern.prefix(3)), target: target,
                                  types: types, usedLines: &usedBridgeLines)

        let sections: [(title: String, lines: [String])] = [
            ("Verse 1", verse1),
            ("Chorus", chorus),
            ("Verse 2", verse2),
            ("Chorus", chorus),
            ("Bridge", bridge),
            ("Chorus", chorus)
        ]

        let text = sections
            .filter { !$0.lines.isEmpty }
            .map { "[\($0.title)]\n" + $0.lines.joined(separator: "\n") }
            .joined(separator: "\n\n")

        guard !text.isEmpty else { throw LyricGenerationError.emptyResponse }
        return GeneratedLyrics(text: text)
    }

    // MARK: - Candidates

    private struct Candidate {
        let template: String
        let text: String
        let image: String?
        let familyIndex: Int
        let syllables: Int
        let lastWord: String
        let rhymeKey: String
        let vowelKey: String
        let hasInternalRhyme: Bool
    }

    /// Expands each template against every available image, so prosody is measured
    /// on the final line text rather than on a placeholder.
    private func buildCandidates(
        families: [[String]],
        images: [String],
        banned: [String],
        usedLines: Set<String>
    ) -> [Candidate] {
        var candidates: [Candidate] = []
        for (familyIndex, family) in families.enumerated() {
            for template in family where !usedLines.contains(template) {
                let variants: [(String, String?)]
                if template.contains("{image}") {
                    variants = images.map { (template.replacingOccurrences(of: "{image}", with: $0), $0) }
                } else {
                    variants = [(template, nil)]
                }
                for (rawText, image) in variants {
                    guard !StyleWordGuard.containsBannedWord(rawText, banned: banned) else { continue }
                    let text = Self.sentenceCased(rawText)
                    let lastWord = ProsodyAnalyzer.lastWord(of: text)
                    candidates.append(Candidate(
                        template: template,
                        text: text,
                        image: image,
                        familyIndex: familyIndex,
                        syllables: ProsodyAnalyzer.syllableCount(inLine: text),
                        lastWord: lastWord,
                        rhymeKey: ProsodyAnalyzer.rhymeKey(for: lastWord),
                        vowelKey: ProsodyAnalyzer.finalVowelGroup(for: lastWord),
                        hasInternalRhyme: ProsodyAnalyzer.hasInternalRhyme(in: text)
                    ))
                }
            }
        }
        return candidates
    }

    /// Imagery is substituted mid-sentence, so a filled line can start lowercase.
    private static func sentenceCased(_ line: String) -> String {
        guard let first = line.first else { return line }
        return first.uppercased() + line.dropFirst()
    }

    private func score(_ candidate: Candidate, target: Int, preferInternal: Bool, usedImages: Set<String>) -> Double {
        var value = -2.0 * Double(abs(candidate.syllables - target))
        if preferInternal && candidate.hasInternalRhyme { value += 5 }
        if let image = candidate.image, usedImages.contains(image) { value -= 1.5 }
        return value
    }

    // MARK: - Stanza selection

    private func selectStanza(
        families: [[String]],
        images: [String],
        banned: [String],
        lineCount: Int,
        pattern: [Character],
        target: Int,
        types: [RhymeType],
        usedLines: inout Set<String>
    ) -> [String] {
        let candidates = buildCandidates(families: families, images: images, banned: banned, usedLines: usedLines)
        guard !candidates.isEmpty else { return [] }

        let preferInternal = types.contains(.internalRhyme)
        // Internal rhyme is a within-line quality; it doesn't say which lines
        // rhyme with each other. If it's the only type chosen, line endings are
        // left free.
        let endTypes = types.filter { $0 != .internalRhyme }
        let pools = rhymePools(from: candidates, types: endTypes)

        let labels = Array(pattern.prefix(lineCount))
        var positionsByLabel: [Character: [Int]] = [:]
        for (index, label) in labels.enumerated() {
            positionsByLabel[label, default: []].append(index)
        }

        var assigned = [Candidate?](repeating: nil, count: lineCount)
        var usedImages = Set<String>()
        var usedLastWords = Set<String>()
        var usedTemplates = Set<String>()
        var usedPoolIDs = Set<Int>()

        // Satisfy the most constrained groups first — a four-line "A" group has
        // far fewer valid options than a singleton.
        let orderedLabels = positionsByLabel.sorted {
            if $0.value.count != $1.value.count { return $0.value.count > $1.value.count }
            return ($0.value.first ?? 0) < ($1.value.first ?? 0)
        }

        for (_, positions) in orderedLabels {
            let needed = positions.count
            var picked: [Candidate]?

            if needed > 1 && !pools.isEmpty {
                picked = choosePool(
                    pools, count: needed, target: target, preferInternal: preferInternal,
                    usedTemplates: usedTemplates, usedImages: usedImages,
                    usedLastWords: usedLastWords, usedPoolIDs: usedPoolIDs
                )
            }
            if picked == nil {
                picked = bestDistinct(
                    candidates, count: needed, target: target, preferInternal: preferInternal,
                    usedTemplates: usedTemplates, usedImages: usedImages, usedLastWords: usedLastWords
                )
            }
            guard let chosen = picked, !chosen.isEmpty else { continue }

            if chosen.count > 1, let rhymeKey = chosen.first?.rhymeKey {
                usedPoolIDs.insert(rhymeKey.hashValue)
            }
            for (offset, position) in positions.enumerated() where offset < chosen.count {
                let candidate = chosen[offset]
                assigned[position] = candidate
                usedTemplates.insert(candidate.template)
                usedLastWords.insert(candidate.lastWord)
                usedLines.insert(candidate.template)
                if let image = candidate.image { usedImages.insert(image) }
            }
        }

        return assigned.compactMap { $0?.text }
    }

    /// Groups of candidates that rhyme with one another. End rhymes use the
    /// authored families directly; slant additionally pools by shared vowel
    /// sound, which lets lines from different families pair up.
    private func rhymePools(from candidates: [Candidate], types: [RhymeType]) -> [[Candidate]] {
        var pools: [[Candidate]] = []
        if types.contains(.end) {
            pools += Dictionary(grouping: candidates, by: \.rhymeKey)
                .values
                .filter { $0.count > 1 }
                .map(Array.init)
        }
        if types.contains(.slant) {
            pools += Dictionary(grouping: candidates.filter { !$0.vowelKey.isEmpty }, by: \.vowelKey)
                .values
                .filter { $0.count > 1 }
                .map(Array.init)
        }
        return pools
    }

    /// Picks the best pool that can supply `count` distinct rhyming lines,
    /// preferring pools not already used by another rhyme group in this stanza
    /// so "AABB" gets two genuinely different rhyme sounds.
    private func choosePool(
        _ pools: [[Candidate]],
        count: Int,
        target: Int,
        preferInternal: Bool,
        usedTemplates: Set<String>,
        usedImages: Set<String>,
        usedLastWords: Set<String>,
        usedPoolIDs: Set<Int>
    ) -> [Candidate]? {
        var best: [Candidate]?
        var bestScore = -Double.greatestFiniteMagnitude

        for pool in pools {
            guard let picked = bestDistinct(
                pool, count: count, target: target, preferInternal: preferInternal,
                usedTemplates: usedTemplates, usedImages: usedImages, usedLastWords: usedLastWords
            ) else { continue }

            var total = picked.reduce(0.0) {
                $0 + score($1, target: target, preferInternal: preferInternal, usedImages: usedImages)
            }
            // Strong nudge toward an unused rhyme sound.
            let poolKey = picked[0].rhymeKey
            if usedPoolIDs.contains(poolKey.hashValue) { total -= 12 }

            if total > bestScore {
                bestScore = total
                best = picked
            }
        }
        return best
    }

    /// Top `count` candidates with distinct source lines and distinct final words
    /// (repeating a word is repetition, not rhyme). Nil if there aren't enough.
    private func bestDistinct(
        _ candidates: [Candidate],
        count: Int,
        target: Int,
        preferInternal: Bool,
        usedTemplates: Set<String>,
        usedImages: Set<String>,
        usedLastWords: Set<String>
    ) -> [Candidate]? {
        let available = candidates
            .filter { !usedTemplates.contains($0.template) && !usedLastWords.contains($0.lastWord) }
            .sorted {
                score($0, target: target, preferInternal: preferInternal, usedImages: usedImages)
                    > score($1, target: target, preferInternal: preferInternal, usedImages: usedImages)
            }

        var seenTemplates = Set<String>()
        var seenLastWords = Set<String>()
        var result: [Candidate] = []
        for candidate in available {
            guard !seenTemplates.contains(candidate.template),
                  !seenLastWords.contains(candidate.lastWord) else { continue }
            seenTemplates.insert(candidate.template)
            seenLastWords.insert(candidate.lastWord)
            result.append(candidate)
            if result.count == count { return result }
        }
        return nil
    }
}

// MARK: - Tone classification

enum LyricTone: String, CaseIterable {
    case melancholy, nostalgic, dreamy, restless, tender, defiant, bittersweet
}

enum ToneClassifier {
    private static let keywords: [LyricTone: [String]] = [
        .melancholy: ["melancholy", "sad", "somber", "sorrow", "grief", "mourning", "heartbroken", "lonely", "aching", "blue", "weep", "cry", "tears", "restrained", "introspective", "sparse", "quiet", "minimal", "subdued"],
        .nostalgic: ["nostalgic", "nostalgia", "memory", "memories", "remember", "childhood", "hometown", "old", "faded", "yesterday", "reminisce", "americana", "roots", "vintage", "retro"],
        .dreamy: ["dreamy", "dream", "hazy", "floating", "ethereal", "cloud", "drifting", "hypnotic", "ambient", "surreal", "weightless", "shoegaze", "atmospheric", "lush", "reverb"],
        .restless: ["restless", "anxious", "racing", "frantic", "urgent", "chaotic", "wild", "runaway", "reckless", "fast", "speed", "escape", "funk", "funky", "driving", "punchy", "energetic", "groove"],
        .tender: ["tender", "love", "gentle", "warm", "intimate", "close", "devotion", "affection", "sweet", "soft", "held", "holding", "acoustic", "delicate", "lullaby"],
        .defiant: ["defiant", "angry", "rebel", "fight", "furious", "bold", "fierce", "rage", "power", "strong", "unstoppable", "proud", "gritty", "raw", "aggressive", "anthemic"]
    ]

    /// The style field leads — it's the explicit instruction about feel — and the
    /// theme prompt only decides the mood when the style says nothing about it.
    static func detect(style: String, prompt: String) -> LyricTone {
        detectIfConfident(in: style) ?? detectIfConfident(in: prompt) ?? .bittersweet
    }

    static func detect(in text: String) -> LyricTone {
        detectIfConfident(in: text) ?? .bittersweet
    }

    /// Returns nil when nothing matches, so callers can fall through to another
    /// source rather than silently defaulting.
    static func detectIfConfident(in text: String) -> LyricTone? {
        let lowered = text.lowercased()
        guard !lowered.isEmpty else { return nil }
        var scores: [LyricTone: Int] = [:]
        for (tone, words) in keywords {
            for word in words where lowered.contains(word) {
                scores[tone, default: 0] += 1
            }
        }
        guard let best = scores.max(by: { $0.value < $1.value }), best.value > 0 else { return nil }
        return best.key
    }

    static func allKeywords(for tone: LyricTone) -> [String] {
        keywords[tone] ?? []
    }
}

// MARK: - Imagery extraction

enum ImageryExtractor {
    private static let stopwords: Set<String> = [
        "a", "an", "the", "and", "or", "but", "of", "in", "on", "at", "to", "for", "with", "about",
        "from", "into", "over", "under", "that", "this", "these", "those", "is", "are", "was",
        "were", "be", "being", "been", "it", "its", "my", "your", "our", "their", "his", "her",
        "i", "you", "we", "they", "he", "she", "so", "as", "by", "up", "out", "if", "not"
    ]
    private static let metaWords: Set<String> = [
        "song", "music", "lyrics", "genre", "style", "mood", "theme", "topic", "track", "tune",
        "ballad", "anthem", "melody", "indie", "folk", "pop", "rock", "country", "electronic",
        "jazz", "blues", "hiphop", "hip", "hop", "rap", "acoustic", "punk", "metal", "soul", "rnb"
    ]
    /// Modifiers read as broken grammar when dropped into a noun slot — "small
    /// gathers dust by the window". Only concrete nouns make usable imagery.
    private static let modifiers: Set<String> = [
        "small", "big", "large", "tiny", "huge", "little", "empty", "full", "dark", "bright",
        "light", "heavy", "loud", "cold", "warm", "hot", "cool", "slow", "fast", "long", "short",
        "last", "first", "next", "good", "bad", "best", "worst", "new", "young", "broken",
        "packed", "lonely", "sad", "happy", "quiet", "wide", "deep", "high", "low", "late",
        "early", "hard", "soft", "clean", "dirty", "open", "closed", "real", "true", "same",
        "every", "some", "many", "much", "more", "most", "less", "least", "just", "very",
        "leaving", "going", "coming", "running", "walking", "driving", "getting", "being"
    ]

    /// Pulls concrete nouns out of the theme prompt and shapes them into noun
    /// phrases so they read correctly wherever a template drops them in.
    /// `excluded` carries the style words, which must never reach the lyrics.
    static func extract(from prompt: String, tone: LyricTone, excluding excluded: [String] = []) -> [String] {
        let toneWords = Set(ToneClassifier.allKeywords(for: tone))
        let words = prompt
            .lowercased()
            .components(separatedBy: CharacterSet.alphanumerics.inverted)
            .filter { $0.count >= 3 }
            .filter { !stopwords.contains($0) && !metaWords.contains($0) && !toneWords.contains($0) }
            .filter { !modifiers.contains($0) }
            .filter { !StyleWordGuard.containsBannedWord($0, banned: excluded) }

        var seen = Set<String>()
        var result: [String] = []
        for word in words where !seen.contains(word) {
            seen.insert(word)
            result.append("the \(word)")
        }
        return Array(result.prefix(6))
    }
}

// MARK: - Hand-written line banks
//
// Each section is a list of *rhyme families* — inner arrays whose lines rhyme
// with one another. This is what lets the generator satisfy a requested rhyme
// scheme. Two rules keep the machinery honest:
//   1. Lines in a family end on genuinely rhyming, differently-spelled words.
//   2. "{image}" never sits at the end of a line, so substituting imagery can
//      never disturb the rhyme.

struct ToneBank {
    let verse: [[String]]
    let chorus: [[String]]
    let bridge: [[String]]
}

enum LineBank {
    static let fallbackImagery: [LyricTone: [String]] = [
        .melancholy: ["the porch light", "an empty room", "the last train", "a cold coffee cup"],
        .nostalgic: ["the backseat window", "an old mixtape", "the kitchen radio", "a faded photograph"],
        .dreamy: ["the static hum", "a slow tide", "the ceiling fan", "soft city lights"],
        .restless: ["the dashboard clock", "a half-packed bag", "the interstate line", "a ringing phone"],
        .tender: ["your old sweater", "the porch swing", "a borrowed jacket", "the space beside me"],
        .defiant: ["the slammed door", "a torn-up letter", "the last word", "a clenched fist"],
        .bittersweet: ["the parking lot lights", "a half-empty glass", "the closing credits", "yesterday's weather"]
    ]

    static let banks: [LyricTone: ToneBank] = [
        .melancholy: ToneBank(
            verse: [
                [
                    "I leave the porch light burning every day",
                    "Your coat still hangs there, folded halfway",
                    "{image} keeps the quiet far away",
                    "I practice all the things I meant to say"
                ],
                [
                    "The coffee in your cup went cold",
                    "I'm keeping every story that you told",
                    "{image} is the only thing I hold",
                    "This house has gotten quiet now, and old"
                ],
                [
                    "I hear the screen door shifting in the night",
                    "The hallway keeps a single bulb alight",
                    "I never got the ending of it right",
                    "{image} disappears before it's light"
                ]
            ],
            chorus: [
                [
                    "I'm learning how to miss you in my sleep",
                    "There's nothing here of yours for me to keep",
                    "The quiet in these rooms has gotten deep",
                    "{image} is a corner I can't sweep"
                ],
                [
                    "I keep the volume low and settle down",
                    "There's no one left to answer in this town",
                    "{image} is the quietest thing I own",
                    "I wear the empty evening like a gown"
                ]
            ],
            bridge: [
                [
                    "Maybe grief is just love with nowhere to stay",
                    "{image} never asks me if I'm okay",
                    "I'm not over it, I'm quieter this way"
                ],
                [
                    "I didn't think I'd learn to be alone",
                    "Your voice still lives inside my phone",
                    "The silence settled in me like a stone"
                ]
            ]
        ),
        .nostalgic: ToneBank(
            verse: [
                [
                    "We raced the dark down Main Street every night",
                    "The streetlights held our names up to the light",
                    "{image} still gets everything half right",
                    "We burned through summer, reckless and too bright"
                ],
                [
                    "I found our initials carved there yesterday",
                    "The porch swing creaks the same two notes all day",
                    "{image} takes me back a hundred miles away",
                    "We had a town too small to make us stay"
                ],
                [
                    "I still can hear the slamming of the door",
                    "We left our shoes in piles across the floor",
                    "{image} is a summer I want more"
                ]
            ],
            chorus: [
                [
                    "We were seventeen and sure and gold",
                    "Nobody warned us how the summers get old",
                    "{image} is a story I've retold",
                    "I keep that year inside a fist I hold"
                ],
                [
                    "Some years just refuse to go away",
                    "I keep replaying one long July day",
                    "{image} is the part I made it stay"
                ]
            ],
            bridge: [
                [
                    "I'm homesick for a version of my own",
                    "The town stayed put; it's only me that's grown",
                    "Everything I miss is something known"
                ],
                [
                    "Nobody tells you memory gets thin",
                    "{image} is a room I can't get in",
                    "We were golden once and didn't know we'd win"
                ]
            ]
        ),
        .dreamy: ToneBank(
            verse: [
                [
                    "The room is underwater, blue and slow",
                    "{image} is a shimmer in the glow",
                    "I'm half awake and letting hours flow",
                    "The morning is a rumor down below"
                ],
                [
                    "The ceiling fan is drawing out a line",
                    "{image} blurs the edges into shine",
                    "Your voice arrives a second behind mine",
                    "Everything is soft and almost fine"
                ],
                [
                    "I lose the afternoon inside the haze",
                    "{image} is a shimmer in the days",
                    "The light comes through in slow and golden rays"
                ]
            ],
            chorus: [
                [
                    "Pull me under, I don't need the ground",
                    "{image} is the softest thing around",
                    "I'm floating loose and coming all unwound",
                    "There's nothing here that's asking to be found"
                ],
                [
                    "Stay with me here where all the edges blur",
                    "{image} is a feeling I prefer",
                    "We're drifting through an hour we defer"
                ]
            ],
            bridge: [
                [
                    "Maybe I dreamed you up before we met",
                    "{image} is a thing I can't forget",
                    "Time moves different and I'm floating yet"
                ],
                [
                    "I don't want the static in me to clear",
                    "{image} is the only thing that's near",
                    "Everything is slow and soft, appear"
                ]
            ]
        ),
        .restless: ToneBank(
            verse: [
                [
                    "The dashboard clock is lying to me now",
                    "{image} is the only thing that's slow somehow",
                    "I'm out the door before I question how",
                    "My foot is tapping out a leaving vow"
                ],
                [
                    "I read the exit signs like they intend",
                    "{image} is a road that doesn't end",
                    "The engine's warmer than the time I spend",
                    "Every red light is a message I won't send"
                ],
                [
                    "I'm packed before I even make a plan",
                    "{image} rattles loose inside the van",
                    "I'm gone the second that the morning ran"
                ]
            ],
            chorus: [
                [
                    "I can't sit still inside a life this small",
                    "{image} is the only thing that's tall",
                    "I'm done with circling the same four wall",
                    "Something in me never learned to stall"
                ],
                [
                    "Give me the highway and a half a tank",
                    "{image} is the only thing to thank",
                    "I'm running from a stillness that went blank"
                ]
            ],
            bridge: [
                [
                    "Maybe I'm not lost, I'm moving fast",
                    "{image} isn't something meant to last",
                    "Staying still was never in the cast"
                ],
                [
                    "I'll figure out the ending on the road",
                    "{image} is a weight I never load",
                    "I'm lighter every mile that I unload"
                ]
            ]
        ),
        .tender: ToneBank(
            verse: [
                [
                    "You fold into the quiet of my day",
                    "{image} is the reason that I stay",
                    "You hum a little off-key either way",
                    "I like the version of me you portray"
                ],
                [
                    "The coffee's cold but I don't mind the day",
                    "{image} is the softest kind of way",
                    "You say my name like it's a thing to say",
                    "I'm learning all your quiet where you stay"
                ],
                [
                    "You leave your sweater on the kitchen chair",
                    "{image} still is holding all your air",
                    "There's nothing on the landing but the stair"
                ]
            ],
            chorus: [
                [
                    "Stay a while, the world can wait outside",
                    "{image} is a place we get to hide",
                    "I'll take the soft forever as a ride",
                    "You're the calm I never knew was wide"
                ],
                [
                    "Close the door and keep this hour small",
                    "{image} is the gentlest thing of all",
                    "You're the only quiet I would call"
                ]
            ],
            bridge: [
                [
                    "I didn't know that gentle could be sure",
                    "{image} is a simple kind of cure",
                    "You make the ordinary days endure"
                ],
                [
                    "I'm not afraid of quiet like this now",
                    "{image} is a promise, not a vow",
                    "You taught me how to settle, and I'm how"
                ]
            ]
        ),
        .defiant: ToneBank(
            verse: [
                [
                    "I stopped requesting room to take my stand",
                    "{image} was never something you command",
                    "You underestimated this whole hand",
                    "I built it out of everything you can't understand"
                ],
                [
                    "I'm done with shrinking down to fit your door",
                    "{image} isn't holding me no more",
                    "The knives came out and I am still on floor",
                    "You'll remember me from days before"
                ],
                [
                    "You mistake my patience for redress",
                    "{image} is a thing you can't possess",
                    "I'm walking out of all of this excess"
                ]
            ],
            chorus: [
                [
                    "I'm not asking twice, I'm telling you now",
                    "{image} won't be stopping me somehow",
                    "I burned the script and took a different bow",
                    "Watch me build it taller than your vow"
                ],
                [
                    "I don't flinch at your version of my name",
                    "{image} is a fire and it's a flame",
                    "I've got nothing left to prove or tame"
                ]
            ],
            bridge: [
                [
                    "This is where I stop apologizing loud",
                    "{image} is a thing I'm saying proud",
                    "I'm stepping out and saying it aloud"
                ],
                [
                    "You had your say and now the floor is mine",
                    "{image} is a hard and holy line",
                    "I'm done pretending everything is fine"
                ]
            ]
        ),
        .bittersweet: ToneBank(
            verse: [
                [
                    "We said goodbye like we meant see you soon",
                    "{image} is a shape beneath the moon",
                    "We laughed right up until the afternoon",
                    "The party emptied out by half past noon"
                ],
                [
                    "I'm happy for you in a smaller voice",
                    "{image} was never really mine by choice",
                    "We got the quiet version of rejoice"
                ],
                [
                    "Some endings linger like a friendly ghost",
                    "{image} is the part I'll miss the most",
                    "We were better than I let on, almost"
                ]
            ],
            chorus: [
                [
                    "It was good while it was ours to keep",
                    "{image} is a thing I couldn't sweep",
                    "I'll miss you in the ordinary deep",
                    "The best of it was never very steep"
                ],
                [
                    "Thank you and goodbye in the same breath",
                    "{image} was a small and gentle death",
                    "We got the ending we were underneath"
                ]
            ],
            bridge: [
                [
                    "Not every good thing had to stay around",
                    "{image} is a comfort I have found",
                    "I'm keeping all the parts that still sound"
                ],
                [
                    "We were lucky, and I think I always knew",
                    "{image} is the part that only grew",
                    "I'd do it all again and still feel new"
                ]
            ]
        )
    ]
}
