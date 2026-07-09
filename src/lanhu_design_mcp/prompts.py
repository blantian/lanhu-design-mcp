ANDROID_UI_RESTORE_PROMPT = """
You are implementing an Android UI from Lanhu design data.

Rules:
- Use platform rect values as dp.
- Keep original px values only as verification metadata.
- Preserve colors, gradients, corner radii, opacity, and text exactly where provided.
- Download and reference assets locally; do not ship remote Lanhu URLs.
- For Android TV, make focusable cards stable in size and do not let focus states change layout.
""".strip()
