# Scope regression caught before next native render

Sourcebc6dfd4 accidentally applied lower-bob width expansion to the hidden long01
alternate too. Pure test rejected X max0.2975m against0.21m envelope. No envelope
check relaxed. Scope the lower-bob expansion to bob02, keep alternate original
width. Run41871208139 cancelled; it is not visual evidence or a successful build.

The corrected source passes six pure checks, including actual source-ID welding
and linear EXR pigment scaling. Full receipt remains separate and must be
reopened/visually reviewed; this note is not a render or artistic certificate.
