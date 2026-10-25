# Product Presentations

Every presentation of DriveTest Analyzer, to present the tool to an audience: those of the tool, the presentation of every main module, of Workspace Config and of Administration, and the **Full Presentation** that joins them all. Help Home shows them too, and each module chapter opens with its own.

## Product Presentation

Present DriveTest Analyzer with its presentations:

- **Overview**, the complete deck: the tool, the teams it serves and its platform, a slide for each module in the order of their tabs (two for Scoring & GAP Analysis) and the roadmap, closing with the one-slider.
- **One-slider**, on a single slide: the most important of the tool, with its figures, modules, teams, platform and what comes next.
- **Roadmap**, on a single slide: what comes next, such as Umlaut CDRs, the Active Tests community, scale-out and speed on AWS, PostgreSQL and health monitoring.
- **Benchmarking Providers Roadmap**, in the design of its own deck: how the tool is being adapted to Umlaut and P3 CDRs and the status of each phase, how it is built inside and how it is deployed in the cloud (see [Benchmarking Providers](benchmarking-providers.md)).

Select a presentation to open it in the slide viewer (its slides on the left and, below the slide, the zoom buttons and **▶ Slideshow**, the arrows of the previous and next slide, **Close** and **Download PowerPoint**; the wheel and the arrow keys also change slide, Ctrl/Cmd+wheel zooms and Escape closes it; on a phone or tablet, swipe the slide to change it, pinch it to zoom and double-tap it for the whole slide, and the viewer fits the part of the screen the browser leaves visible, with the arrows of the slides first), play it full screen with **▶ Slideshow**, choosing the seconds per slide and the transition, or download it with **Download PowerPoint**. **Copy link**, on each card and beside **Close** in the viewer, copies the short link of the presentation (in the viewer, of the slide shown), such as `/presentations/full-presentation?slide=3`, to send it: opening it opens the presentation at that slide in the slide viewer of this chapter, also without signing in. The link has the **Public address** of the server when [Application Config](app-config.md) has one, otherwise the address the application was opened with. Where the link is shared (WhatsApp, Teams, Slack, Outlook…), its preview shows the title of the presentation, its description and the picture of that slide (the link of this chapter, the cover of the Full Presentation), when the app can reach the server; WhatsApp on Android opens no link with an IP address (nor shows its preview), so give the server a name and save it as its public address. While a presentation is open, the address of the page is that link too. The server generates every presentation, with the pictures of its slides, always in the background, so the application never waits for them: at its start when one is missing (until it is ready, the Help says it is coming), again when their figures or the generator change, and on demand with **Regenerate Presentations** in [Super Admin → Presentations](super-admin.md#presentations). The figures of the first three are live: those of the workspaces chosen there.

```presentations
overview
one-slider
roadmap
benchmarking-providers
```

## Module presentations

Each main module also has a presentation of its own, in a design of its own, at the start of its chapter: [Workspace Management](workspace-management.md), with **Workspace Config** after it (everything to set up in a new workspace: how operators, vendors and campaigns are named, coloured and ordered, the map areas of its countries, its networks and its methodology; see [Workspace Config](workspace-config.md)), [CDR Analysis](datasets-analysis.md), [PPT Dashboards](ppt-dashboards.md), [Scoring & GAP Analysis](scoring-gap-analysis.md), [Network Insights](network-insights.md), [Non-Qualified Calls](non-qualified-calls.md) with the **DT Analyzer RCA** beside it (how it finds the root cause of every Non-Qualified Call: what it reads, its rules, the lack of resources, the network around the call and the evidence it gives), [Reporting](reporting.md), [Builders](chart-builder.md) and [Ticket Center](ticket-center.md), and **Administration** after them (Admin and Super Admin: users and access, the databases, backups, packages and transfers, the configuration of the application at every level and App Events; see [Super Admin](super-admin.md)). They open in the same slide viewer and download as PowerPoint.

```presentations
workspace
workspace-config
cdr-analysis
ppt-dashboards
scoring-gap-analysis
network-insights
non-qualified-calls
dt-analyzer-rca
reporting
builders
ticket-center
administration
```

## Full presentation

The **Full Presentation** joins every presentation in one deck, with their slides as they are, each in a section named after it: the Overview, the presentation of every main module (with Workspace Config after Workspace) and of Administration, the DT Analyzer RCA, the Benchmarking Providers Roadmap and the Roadmap. It opens in the same slide viewer and downloads as PowerPoint.

```presentations
full-presentation
```
