# canvas-web-design-mode Specification

## Purpose
TBD - created by archiving change canvas-web-publish-portal. Update Purpose after archive.
## Requirements
### Requirement: Canvas mode selector includes Web Page Design option
The workspace panel canvas mode picker SHALL expose a third option — **Web Page Design** — alongside the existing Free Layout and Fixed Size modes. Selecting this mode replaces the React Flow surface with the structured web-page editor.

#### Scenario: Mode appears in picker
- **WHEN** the user opens the canvas mode selector in the workspace panel
- **THEN** the picker displays three options: "Free Layout", "Fixed Size", and "Web Page Design"

#### Scenario: Switching to Web Page Design
- **WHEN** the user selects "Web Page Design"
- **THEN** the React Flow canvas is hidden and the structured section-grid editor is rendered in its place, preserving any charts already in the workspace as unplaced items in a sidebar tray

### Requirement: Section-grid layout with column and row configuration
In Web Page Design mode the editor SHALL render the page as a CSS grid. Users can configure the number of columns (2–6) and add or remove horizontal rows. Each row has a configurable height (min 120 px, max 800 px).

#### Scenario: Default grid
- **WHEN** Web Page Design mode is entered for the first time on a workspace
- **THEN** the grid initializes with 3 columns and 2 rows at 400 px height each

#### Scenario: Column count change
- **WHEN** the user changes the column count in the grid toolbar
- **THEN** all existing zones are remapped to the nearest valid cell positions without data loss; zones wider than the new column count are clamped to the maximum span

#### Scenario: Row addition
- **WHEN** the user clicks "Add Row"
- **THEN** a new row is appended at the bottom with the default height of 400 px

### Requirement: Constrained chart zones
A chart zone is a grid cell or a spanning cell that holds exactly one chart or one text block. Zones SHALL snap to grid cell boundaries. Resize handles allow the zone to span additional columns or rows but MUST NOT allow the zone to shrink below 1×1 cells or grow beyond the grid boundary.

#### Scenario: Zone placement from tray
- **WHEN** the user drags a chart from the unplaced items tray onto an empty grid cell
- **THEN** a chart zone is created occupying that cell, rendering the chart inside it

#### Scenario: Zone resize stays within grid
- **WHEN** the user drags a zone's resize handle to expand it
- **THEN** the zone grows by integer column/row increments only, and cannot overlap an occupied cell or exceed the grid boundary

#### Scenario: Zone minimum size enforcement
- **WHEN** the user attempts to shrink a zone below 1 column or 1 row
- **THEN** the resize is rejected and the zone remains at its current minimum span

### Requirement: Multi-level sidebar editor
The Web Page Design editor SHALL include a sidebar editor panel where users define a two-level navigation structure: top-level sections and optional sub-sections under each. Each section or sub-section links to a named anchor in the page grid.

#### Scenario: Add a top-level section
- **WHEN** the user clicks "Add Section" in the sidebar editor
- **THEN** a new top-level section entry is added with a default label "Section N" and no sub-sections

#### Scenario: Add a sub-section
- **WHEN** the user clicks "Add Sub-section" under an existing section
- **THEN** a sub-section entry is added under that section, indented visually

#### Scenario: Link section to page anchor
- **WHEN** the user selects a grid row in the "Links to" dropdown for a sidebar entry
- **THEN** clicking that sidebar entry in the published page smoothly scrolls to the top of the linked row

#### Scenario: Maximum nesting depth
- **WHEN** the user attempts to add a sub-section under an existing sub-section
- **THEN** the action is blocked and the system shows a tooltip: "Sidebar supports two levels only"

### Requirement: Live preview of published layout
The Web Page Design editor SHALL show a toggle between "Edit" and "Preview" mode. In Preview mode the canvas renders as it will appear in the published portal, including the sidebar navigation, chart zones with chart content, and text blocks — but without editing controls.

#### Scenario: Switch to preview
- **WHEN** the user clicks "Preview"
- **THEN** all editing handles, the grid overlay, and the sidebar editor panel are hidden; the layout renders in its published appearance

#### Scenario: Return to edit
- **WHEN** the user clicks "Edit" while in Preview mode
- **THEN** editing controls are restored exactly as they were before entering Preview

