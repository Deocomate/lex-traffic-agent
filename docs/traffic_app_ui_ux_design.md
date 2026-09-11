> [!WARNING]
> **TÀI LIỆU ĐÃ HẾT HIỆU LỰC (DEPRECATED)**  
> Tài liệu này phản ánh đặc tả thiết kế cũ trước tháng 09/2026 (sidebar navy đặc, 3 họ font chữ, cỡ chữ 13.5px).  
> Toàn bộ giao diện LexTraffic AI hiện tại đã được chuyển đổi sang Hệ thiết kế Tối giản (Minimal Design System) thuần tokens CSS.  
> **Nguồn chuẩn hiện tại:** Vui lòng tham khảo tài liệu chính thức tại [`docs/design-system.md`](file:///c:/Users/minhlong/Desktop/evo/ai-giaothong/docs/design-system.md).

# 📘 LexTraffic AI — Desktop UX/UI Design Specification (1440px Widescreen)

> **Platform:** LexTraffic AI — SOTA AI-Powered Traffic Law Assistant  
> **Target Viewport:** 1440px Desktop Baseline (Widescreen multi-column layout)  
> **Design Philosophy:** Modern Professional LegalTech Authority & Human-Centered Usability  
> **Legal Baseline:** Luật Trật tự, an toàn giao thông đường bộ 2024 (Luật số 36/2024/QH15) & Nghị định số 100/2019/NĐ-CP (sửa đổi, bổ sung bởi Nghị định 123/2021/NĐ-CP).

---

## 🎨 1. Core Visual Identity & Design Tokens

LexTraffic AI communicates **credibility, judicial precision, and executive calm**. The visual system eschews distracting flashy effects in favor of clean structure, crisp 1px borders, generous whitespace, and high-contrast legal typography.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             LEXTRAFFIC COLOR SYSTEM                         │
├──────────────────────┬──────────────────────┬───────────────────────────────┤
│ Deep Navy (#1E293B)  │ Emerald (#10B981)    │ Amber Orange (#F59E0B)        │
│ Primary Authority    │ Safe Compliance      │ Penalties, Fines & Points     │
├──────────────────────┼──────────────────────┼───────────────────────────────┤
│ Canvas (#F8FAFC)     │ Surface (#FFFFFF)    │ Borders (#E2E8F0 / #CBD5E1)   │
│ Off-White Background │ Pure White Cards     │ Crisp 1px Structural Lines    │
└──────────────────────┴──────────────────────┴───────────────────────────────┘
```

### 1.1 Color Tokens

| Token Name | Hex Code | HSL / RGB | Purpose & Usage |
| :--- | :--- | :--- | :--- |
| `--primary-900` | `#0F172A` | `rgb(15, 23, 42)` | Sidebar background, modal backdrop, ultra-dark text |
| `--primary-800` | `#1E293B` | `rgb(30, 41, 59)` | **Primary Brand Color**: Navigation headers, active states, buttons |
| `--primary-700` | `#334155` | `rgb(51, 65, 85)` | Subheaders, dark borders, secondary text icons |
| `--emerald-500` | `#10B981` | `rgb(16, 185, 129)` | **Safe Compliance Accent**: Verified citations, 0-fine states, active status |
| `--emerald-50` | `#ECFDF5` | `rgb(236, 253, 245)` | Compliance badges background, legal confirmation highlights |
| `--amber-500` | `#F59E0B` | `rgb(245, 158, 11)` | **Penalty & Liability Accent**: Fine amounts, points deducted, urgent alerts |
| `--amber-50` | `#FFFBEB` | `rgb(255, 251, 235)` | Fine receipt highlight banner, active focus clause background |
| `--bg-canvas` | `#F8FAFC` | `rgb(248, 250, 252)` | **Clean Off-White**: Desktop main background canvas |
| `--bg-surface` | `#FFFFFF` | `rgb(255, 255, 255)` | Card components, document paper, top bar surface |
| `--border-subtle` | `#E2E8F0` | `rgb(226, 232, 240)` | Crisp 1px divider lines, component borders |
| `--border-strong` | `#CBD5E1` | `rgb(203, 213, 225)` | Card boundaries, interactive input borders |

---

### 1.2 Typography & Scale System

The interface pairs **Plus Jakarta Sans** (authoritative modern geometric sans-serif for headings) with **Inter** (optimized for dense, multi-paragraph statutory reading) and **JetBrains Mono** (for exact legal citations, Decree numbers, and speed/currency metrics).

| Role | Font Family | Size | Weight | Line Height | Tracking |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Display H1** | Plus Jakarta Sans | `34px` | 800 (Bold) | `1.2` | `-0.025em` |
| **Section H2** | Plus Jakarta Sans | `26px` | 800 (Bold) | `1.25` | `-0.02em` |
| **Card / Modal H3** | Plus Jakarta Sans | `18px` | 700 (Bold) | `1.3` | `-0.015em` |
| **Subhead H4** | Inter | `15px` | 700 (SemiBold)| `1.4` | `-0.01em` |
| **Body (Default)** | Inter | `14px` | 400 / 500 | `1.6` | `0` |
| **Statutory Text** | Inter | `14px` | 400 / 500 | `1.75` | `0` (Max readability) |
| **Micro Labels** | Inter | `11px - 12px`| 600 (SemiBold)| `1.4` | `+0.04em` (Uppercase) |
| **Legal Citations** | JetBrains Mono | `12px - 13px`| 600 (Medium) | `1.5` | `0` |

---

## 🏛️ 2. Desktop 1440px Multi-Column Architecture

The application adopts a **240px fixed left sidebar** paired with a fluid **1200px widescreen workspace** contained within a max-width 1440px viewport frame.

```
┌───────────┬─────────────────────────────────────────────────────────────────┐
│           │ TOPBAR (68px): Screen Switcher | Global Search | Notifications  │
│           ├─────────────────────────────────────────────────────────────────┤
│           │ [Screen 1: Landing & Central AI Dashboard]                      │
│           │  - Hero Query Card (Massive Voice/Text Input + Sample Chips)    │
│           │  - Quick-Access Grid (4 Cards: Alcohol, Speed, Revoke, Urban)   │
│           │  - Legislative Authority Standardization Banner                 │
│  SIDEBAR  ├─────────────────────────────────────────────────────────────────┤
│  (240px   │ [Screen 2: Split-Screen AI Chat & Legal Source Viewer]          │
│   Fixed)  │  ┌──────────────────────────────┬─────────────────────────────┐ │
│           │  │ AI Chat Stream (40% Width)   │ Legal Document (60% Width)  │ │
│           │  │ - Bold Verdict Summary Card  │ - Gov Header & Full Decree  │ │
│           │  │ - Follow-up Suggestion Chips │ - Jargon Tooltip Triggers   │ │
│           │  │ - Voice Dictation Input Bar  │ - Toolbar: Bookmark/PDF/Copy│ │
│           │  └──────────────────────────────┴─────────────────────────────┘ │
│           ├─────────────────────────────────────────────────────────────────┤
│           │ [Screen 3: Advanced Desktop Fine & Penalty Calculator]          │
│           │  ┌──────────────────────────────┬─────────────────────────────┐ │
│           │  │ 2-Col Data Entry Form (Left) │ Digital Receipt Board (R)   │ │
│           │  │ - Vehicle Class (4 Tiles)    │ - Giant Amber Fine Display  │ │
│           │  │ - Violation Category Dropdown│ - Points & Revocation Status│ │
│           │  │ - Dual Real-time Sliders     │ - Statutory Citation        │ │
│           │  │ - Aggravating Circumstances  │ - "Initiate AI Dispute Chat"│ │
│           │  └──────────────────────────────┴─────────────────────────────┘ │
└───────────┴─────────────────────────────────────────────────────────────────┘
```

---

## 📱 3. Screen-by-Screen UX/UI Specifications

### Screen 1: Desktop Landing & Central AI Dashboard
- **Sidebar (240px fixed)**:
  - Header: LexTraffic AI brand logo with balance scale icon + "2024 Compliance" badge.
  - Menu Items: *Central AI Dashboard*, *AI Legal Assistant*, *Fine Calculator*, *Saved Bookmarks*, *Search History*, *Decree Updates*.
  - Live Database Status Card: Shows `Database v2024.3 Live` with pulsing emerald indicator dot.
- **Top Bar (68px)**:
  - Rapid Screen Switcher Pills: Instant navigation between Dashboard, Split View, and Fine Calculator.
  - Universal Quick Search (`⌘K`) with input focus feedback.
  - Legal decree tag pill: `Luật 36/2024 & NĐ 100/123`.
  - Notification drawer button & User profile badge.
- **Hero Search Section**:
  - Elevated central search card with placeholder: *"Ask LexTraffic AI anything (e.g., 'What is the penalty for a car speeding 15km/h over the limit in a residential area?')"*.
  - **Voice Input Button**: Microphone trigger with live audio waveform animation bar simulating active speech dictation.
  - One-click legal prompt chips for instant query execution.
- **Quick-Access Grid (4 Interactive Cards)**:
  1. **Alcohol Fine Breakdown** (Amber icon): 3 BAC tiers (0 to >0.4 mg/l), fines & mandatory impoundment.
  2. **Speed Limit Matrix** (Blue icon): Speed limits in residential areas vs expressways and violation brackets.
  3. **License Revocation Conditions** (Rose icon): License seizure durations (1–24 months) & point deductions.
  4. **Common Commuter Violations** (Emerald icon): Top 25 city commuter infractions.

---

### Screen 2: Split-Screen AI Chat & Legal Source Viewer (The Core Experience)
- **Left Panel (40% width - Continuous AI Chat Stream)**:
  - Header: `LexTraffic AI Assistant` with `Verified Legal Cite` badge.
  - User Query Bubble: *"What happens if I refuse an alcohol breathalyzer test?"*
  - **AI Answer Card**:
    - **Bold Verdict Summary**: *"Phạt tiền từ 30.000.000đ – 40.000.000đ và Tước quyền sử dụng Giấy phép lái xe từ 22 – 24 tháng đối với người điều khiển xe ô tô."*
    - Administrative breakdown: Immediate 7-day vehicle impoundment, motorbike refusal contrast.
    - **Statutory Anchor Box**: Clickable card linking directly to *Điểm a Khoản 10 Điều 5 NĐ 100/2019/NĐ-CP*, automatically scrolling and highlighting the right pane.
    - **Smart Follow-up Suggestion Chips**:
      - *"🩸 Yêu cầu xét nghiệm máu thay thế?"*
      - *"🏷️ Máy đo không có tem kiểm định?"*
      - *"⚖️ Quy trình khiếu nại biên bản"*
  - Bottom Bar: Dictation mic, input box, send button.
- **Right Panel (60% width - Legal Source Reference Document)**:
  - Top Toolbar: Decree Selector (`NĐ 100/2019` vs `Luật 36/2024`), `Bookmark Clause`, `Copy Text`, `Export PDF`.
  - Document Paper Viewport: Official Vietnamese Government Decree Format (National Motto, Decree Number, Chapter II, Article 5).
  - **Active Focus Clause**: Highlighted in amber border with active pulse effect.
  - **Interactive Legal Jargon Tooltips**:
    - Term 1: `phương tiện giao thông cơ giới đường bộ` -> Statutory definition popup.
    - Term 2: `Không chấp hành yêu cầu kiểm tra` -> Officer authority and procedural scope.
    - Term 3: `tước quyền sử dụng Giấy phép lái xe` -> Administrative sanction legal meaning.

---

### Screen 3: Advanced Desktop Penalty & Fine Calculator
- **Left Grid Form (2-Column Desktop Data Entry)**:
  - **Vehicle Class Tiles**: 4 interactive cards (`Xe Ô Tô`, `Xe Mô Tô`, `Xe Tải / Bus`, `Xe Máy Điện`).
  - **Violation Group Dropdown**: Speeding, Alcohol/BAC, Traffic Light, Lane Deviation, Documentation.
  - **Road Type Dropdown**: Residential Area, Expressway/Highway, Rural Area.
  - **Dual Interactive Parameter Sliders**:
    - Slider 1: Allowed Road Speed (30 – 120 km/h) [Default: 50 km/h].
    - Slider 2: Recorded Speed (30 – 160 km/h) [Default: 68 km/h].
    - Real-time calculation readout: `+18 km/h (Khung 10 - 20 km/h)`.
  - **Aggravating Factors**: Checkboxes for traffic accident occurrence or missing registration papers.
- **Right Result Board (Digital Legal Receipt Layout)**:
  - Receipt Header: `ASSESSMENT #LT-2024-8842`.
  - **Giant Amber Fine Display**: `4.000.000 – 6.000.000 ₫` (Midpoint recommendation: `5.000.000 ₫`).
  - Itemized Assessment Table: Vehicle type, violation behavior, License Point deduction (`Trừ 02 Điểm (2 / 12)`), License revocation duration, Vehicle impoundment advisory.
  - Legal Citation: Formal statutory reference.
  - **Primary CTA Button**: **"Initiate AI Dispute Chat regarding this calculation"** — transfers calculation state seamlessly into Screen 2 split-chat with custom legal consultation prompt.
  - **Secondary CTA Button**: **"In / Xuất Phiếu Thẩm Định Vi Phạm"** (`window.print()`).

---

## ⚡ 4. Micro-Interactions & State Management

1. **Screen Switch Transitions**:
   - 200ms cubic-bezier fade and subtle Y-axis elevation for zero disorientation.
2. **Dynamic Live Calculations**:
   - Sliding the speed controls immediately re-evaluates violation tier, monetary fine range, driver point deductions, and updates the receipt board with zero lag.
3. **Legal Jargon Tooltip Hovers**:
   - 150ms ease-in tooltips with dark popover cards (`#0F172A`), emerald header badges, and pointer triangles.
4. **Voice Dictation Simulation**:
   - Micro-animation of 5 oscillating waveform bars simulating audio frequency analysis.
5. **Toast Notification System**:
   - Floating dark pill notification on bottom-right confirming clipboard actions, bookmark saves, and decree updates.

---

## ♿ 5. Accessibility & Web Performance Standards

- **Contrast Ratios**: Normal text meets WCAG AA (min 4.5:1); headers and amber accent blocks exceed 7:1 against dark backgrounds.
- **Keyboard Navigation**: Full Tab order support with `⌘K` global search shortcut.
- **Semantic HTML5**: Native `<main>`, `<aside>`, `<nav>`, `<header>`, `<section>`, `<label>`, `<button>` structure without div-soup.
- **Zero Heavy Dependencies**: Pure Vanilla CSS and lightweight modern Vanilla JS for sub-100ms first paint and 60 FPS desktop animations.
