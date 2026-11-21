\## Libraries and tools

| Name | Version | Licence | Used for | Status |

|---|---|---|---|---|

| FFmpeg (Gyan build, includes libx264) | 9.1 | GPL build, run as an external process only | Video and audio processing | verified from build flags (--enable-gpl) |

| faster-whisper | 1.2.1 | MIT | Speech to text with word timings | verified (pip metadata) |

| Piper voice en_US-ljspeech-medium | Public domain (per MODEL_CARD; dataset: LJ Speech, keithito.com/LJ-Speech-Dataset) | Narration voice | verified |
| open\_clip\_torch | 4.2.2 | MIT | Matching footage to text by meaning | verified (pip metadata) |

| sentence-transformers | 6.3.0 | Apache-2.0 | Text embeddings | verified (pip metadata) |

| PyTorch (CPU) | 2.15.0+cpu | Apache-2.0, BSD, MIT and others | Runs the models | verified (pip metadata) |

| FastAPI | 0.165.0 | MIT | HTTP API | verified (pip metadata) |

| httpx | 0.28.1 | BSD-3-Clause | HTTP client for footage APIs | verified (pip metadata) |
- Amy voice was evaluated and rejected: repo licence is CC BY-SA 4.0 with an unresolved ShareAlike question and a mixed training history. LJSpeech is used instead.


\## Models and weights

| Name | Licence | Used for | Status |

|---|---|---|---|

| Whisper base (via faster-whisper) | verify on model card | Transcription | verify |

| Piper voice en\_US-amy-medium | verify on MODEL\_CARD | Narration voice | verify |

| CLIP weights (exact pretrained tag TBD) | verify on model card | Matching | verify |

| all-MiniLM-L6-v2 (if used) | verify on model card | Text embeddings | verify |



\## Footage and media

| Source | Licence | Attribution | Restrictions that affect this project | Status |

|---|---|---|---|---|

| Pixabay API | Pixabay Content Licence | Not required; link and ID still recorded per clip | No standalone resale of clips. No misleading use. Logos/trademarks in a clip can't be used commercially for goods or services. Third-party consent for people/brands is not cleared. No bulk copying of the library | verifie; API usage rules: verify |

| NASA Image and Video Library | NASA media guidelines (not a blanket public-domain grant) | Credit "NASA" | No implied NASA endorsement. NASA logos not allowed. Identifiable people need permission for commercial use. Some items are third-party owned | verified. Used as a restricted fallback source |



\## Footage rules in the engine



These rules come from the Pixabay and NASA terms above. They are planned behaviour; each one is marked "planned" until implemented and tested.



1\. \*\*Record provenance for every clip.\*\* timeline.json stores source name, clip ID, page link, licence name and attribution text. (planned)

2\. \*\*Commercial-use sources only.\*\* Only providers whose licence allows commercial use are enabled in the default path. (planned)

3\. \*\*No watermarked footage.\*\* Clips flagged as watermarked or with a "preview" or "sample" URL are skipped. (planned)

4\. \*\*Avoid recognisable people and logos.\*\* Candidates are filtered with the user's `avoid` list plus a default rule against recognisable faces and visible brand logos. This follows the Pixabay restriction on people and trademarks. (planned)

5\. \*\*NASA is a restricted fallback.\*\* NASA clips are used only when Pixabay returns nothing suitable. Each NASA clip adds a warning to manifest.json ("NASA media: no implied endorsement"). Clips that mention third-party ownership, identifiable people or NASA insignia are excluded. (planned)

6\. \*\*No bulk copying.\*\* The engine searches per scene and downloads only the clip it selects, never a whole library. (planned)

7\. \*\*No standalone redistribution.\*\* Output is always edited video with narration and captions. Raw source clips are never offered as a deliverable. (planned)

8\. \*\*No misleading use.\*\* Sensitive topics (sad news) get neutral, respectful footage, and named people or brands get no clips that imply their involvement. (planned)

9\. \*\*AI-generated clips are flagged.\*\* Any generated clip gets `ai\_generated: true` in timeline.json and manifest.json. (not used so far)

10\. \*\*Keys stay out of the repo.\*\* Provider keys come from environment variables only. (done: .env is gitignored)

