# Fine-Grained Lanhu Design Assets Design

## Goal

Enhance the existing `lanhu_get_design_assets` MCP tool so it returns both the full design image and fine-grained slice assets declared by Lanhu, while preserving the current tool name and arguments.

The implementation will reuse the proven slice extraction behavior from `/Users/buluesky/mcp/lanhu-mcp/lanhu_mcp_server.py` without importing that project's unrelated prompt, collaboration, download, or document-processing features.

## Research Findings

The current service returns only one `design_image` asset and explicitly defers fine-grained slice export. Its compact DDS DesignIR does not retain enough source data to discover downloadable slices.

The upstream `lanhu-mcp` project already implements the required behavior in `LanhuExtractor.get_design_slices_info`, `_build_scale_urls`, and `_build_ps_scale_urls`. It supports:

- Sketch JSON under `info[]`, with assets in `image` or legacy `ddsImage`;
- Figma JSON under `artboard.layers[]`, accepting exported bitmap layers and excluding image-fill layers;
- Photoshop JSON, where `assets[].isSlice` entries reference layer resources;
- PNG and SVG resource URLs;
- Web, iOS, and Android scale-specific URLs;
- logical size, canvas position, parent name, layer path, and optional visual metadata.

A read-only probe against the existing `子模块` design confirmed that its version `json_url` contains a Sketch slice named `切换` with `type: "slice"`, `exportable: true`, a 22 by 22 logical frame, and both PNG and SVG URLs. This proves that the version SketchJSON, rather than the compact DDS schema, is the correct extraction source.

## Architecture

### Asset extraction module

Create `src/lanhu_design_mcp/design_assets.py` as a pure data-processing module. It will:

- traverse Sketch, Figma, and Photoshop source structures;
- distinguish downloadable slices from non-exported image fills;
- normalize source records into one slice asset shape;
- generate scale-specific URLs;
- deduplicate assets;
- sanitize suggested filenames.

The module will not perform HTTP requests, read configuration, register MCP tools, or write downloaded files.

### Client responsibilities

Extend `LanhuClient` with a method that:

1. fetches design metadata through the existing `/api/project/image` request;
2. selects the latest version's `json_url`;
3. fetches and returns the version SketchJSON plus the version metadata needed by the service.

Authentication and HTTP error handling remain client responsibilities.

### Service orchestration

Refactor `DesignService.get_design_assets` so it does not call `analyze_design`. It will:

1. parse the Lanhu URL;
2. list and resolve the selected design using the existing selector rules;
3. retain the full design image as the first asset;
4. fetch the version SketchJSON;
5. invoke the pure extractor;
6. append normalized slice assets;
7. return asset counts, slice scale, and any warnings.

`DesignService.export_ui_context` will continue calling `get_design_assets`, so it automatically receives the enhanced asset list. `lanhu_analyze_design` and the compact DesignIR remain unchanged.

### MCP surface

Keep the public tool unchanged:

```python
lanhu_get_design_assets(
    url: str,
    design_name_or_index: str | None = None,
    target_platform: Literal["web", "android", "ios", "wechat_miniprogram"] = "android",
) -> dict
```

Do not add a separate `lanhu_get_design_slices` tool because it would overlap with the enhanced asset tool.

## Asset Contract

The existing top-level fields remain available. Successful results add `slice_scale`, `total_assets`, and `total_slices`.

```json
{
  "status": "success",
  "project": {"id": "project-id", "name": "project-name"},
  "design": {"id": "design-id", "name": "design-name"},
  "target_platform": "android",
  "slice_scale": 2,
  "total_assets": 2,
  "total_slices": 1,
  "assets": [
    {
      "kind": "design_image",
      "name": "design-name.png",
      "remote_url": "https://example.invalid/design.png",
      "suggested_local_path": "assets/lanhu/design-id/design-name.png"
    },
    {
      "kind": "slice",
      "id": "layer-id",
      "name": "切换",
      "type": "slice",
      "format": "png",
      "remote_url": "https://example.invalid/slice.png",
      "svg_url": "https://example.invalid/slice.svg",
      "scale_urls": {
        "1x": "https://example.invalid/slice.png?resize-1x",
        "2x": "https://example.invalid/slice.png",
        "android_xhdpi": "https://example.invalid/slice.png?resize-xhdpi"
      },
      "logical_size": {"width": 22, "height": 22},
      "position_px": {"x": 1241, "y": 66},
      "parent_name": "切换",
      "layer_path": "切换",
      "suggested_local_path": "assets/lanhu/design-id/切换.png"
    }
  ],
  "warnings": []
}
```

Contract rules:

- The full design image is always the first asset.
- `remote_url` is the original stored Lanhu resource URL; it is not replaced according to `target_platform`.
- `scale_urls` contains every scale that can be generated from a PNG source.
- When PNG and SVG both exist, `format` and `remote_url` refer to PNG and `svg_url` preserves the vector alternative.
- SVG-only assets use `format: "svg"`, use the SVG URL as `remote_url`, and omit `scale_urls`.
- `logical_size`, `position_px`, `parent_name`, `layer_path`, and `metadata` are included only when source data exists.
- `target_platform` remains in the response for compatibility and downstream selection; the tool does not silently replace the original URL with a platform-specific URL.
- Suggested local paths remain under `assets/lanhu/<design-id>/` and use sanitized source names. Duplicate filenames receive a deterministic numeric suffix.
- `total_assets` includes the full design image; `total_slices` counts only `kind: "slice"` entries.

## Source Compatibility Rules

### Sketch

Traverse `info[]` and nested `layers` or `children`. Accept records containing a usable `image.imageUrl`, `image.svgUrl`, or legacy `ddsImage.imageUrl`. Prefer `image.size`, falling back to `frame`, `bounds`, `layerOriginFrame`, or `ddsOriginFrame` for logical dimensions and position.

### Figma

Detect Figma from `meta.host.name == "figma"`. Traverse `artboard.layers[]` and nested children. Accept `image` resources only when `hasExportImage` is true. Do not treat `ddsImage` or non-exported `image` records as slices because these commonly represent image fills.

### Photoshop

When the root type is `ps`, index layers by ID from `board`, `info`, and their descendants. For each `assets[]` record with `isSlice: true`, find the matching layer and read `images.png_xxxhd` or `images.svg`. Use the upstream Photoshop base-pixel convention when producing logical sizes and scaled URLs.

## Scale URL Rules

Port the upstream scale calculations without semantic changes:

- PNG resize URLs use Lanhu OSS `x-oss-process=image/resize` parameters.
- Web keys are `1x`, `2x`, and `3x`.
- iOS keys are `ios_1x`, `ios_2x`, and `ios_3x`.
- Android keys are `android_mdpi`, `android_hdpi`, `android_xhdpi`, `android_xxhdpi`, and `android_xxxhdpi`.
- JavaScript-compatible rounding uses `floor(value + 0.5)` for positive pixel dimensions.
- If a requested output size equals the stored PNG size, return the original URL without an OSS query.
- SVG sources do not receive raster scale URLs.

## Error Handling

- Authentication failures, project-list failures, and design-selection failures remain hard errors because the requested design cannot be identified reliably.
- If version metadata has no `json_url`, the JSON request fails, or the source document cannot be parsed, return the full design image with `status: "partial_success"`, `total_slices: 0`, and a human-readable warning.
- A malformed individual layer is skipped without aborting extraction of other layers. The response warning states how many candidate layers were skipped.
- Deduplicate slice assets by the pair `(id, remote_url)`. Records without an ID are deduplicated by `(layer_path, remote_url)`.
- Sanitize `/`, `\`, control characters, and path traversal segments in suggested filenames.
- The MCP server does not download or write asset files in this feature.

## Testing

### Pure extractor tests

Add focused fixtures and assertions for:

- the observed Sketch `切换` slice with PNG and SVG URLs;
- legacy Sketch `ddsImage` extraction;
- Figma exported bitmap acceptance;
- Figma image-fill rejection;
- Photoshop `assets[].isSlice` association;
- nested layer paths and optional metadata;
- missing size fallbacks;
- deterministic deduplication and filename collision handling;
- Web, iOS, and Android scale URLs;
- JavaScript-compatible half-up rounding;
- SVG-only assets;
- malformed candidate layers.

### Client and service tests

Use mocked HTTP/service dependencies to verify:

- latest-version SketchJSON retrieval;
- successful combined full-image and slice response;
- no-slice success response;
- partial success when `json_url` is unavailable or invalid;
- selector behavior remains unchanged;
- `export_ui_context` includes the enhanced assets.

### Real smoke test

Run a read-only smoke test with the configured Lanhu cookie against the existing `子模块` design. Verify that the result contains the full design image and the `切换` slice, that both PNG and SVG URLs are present, and that the remote resources respond successfully. Do not download assets into the repository.

## Non-Goals

- Writing downloaded assets to a caller's repository.
- Semantic translation or AI-driven renaming of layer names.
- Adding an overlapping `lanhu_get_design_slices` MCP tool.
- Changing DDS DesignIR extraction or platform-unit conversion.
- Copying upstream workflow prompts, project detection, message-board behavior, or unrelated Lanhu document features.
