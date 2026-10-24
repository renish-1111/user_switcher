// Floating quick user switcher. Loaded on both Desk (app_include_js) and website
// pages (web_include_js), so it only relies on jQuery + frappe.call, which exist in both.
(function () {
	const API = "user_switcher.api";
	const CACHE_KEY = "user_switcher_allowed";
	const HIDDEN_KEY = "user_switcher_hidden";
	const BANNER_KEY = "user_switcher_banner_collapsed";
	const USAGE_KEY = "user_switcher_usage";
	const PINS_KEY = "user_switcher_pins";
	const LEGACY_RECENT_KEY = "user_switcher_recent";
	const MAX_MOST_USED = 5;
	// Ctrl+S is Frappe's Save, so the switcher uses Ctrl+Shift+S
	const SHORTCUT_LABEL = "Ctrl+Shift+S";
	const is_open_shortcut = (e) => (e.ctrlKey || e.metaKey) && e.shiftKey && !e.altKey && e.code === "KeyS";
	// Straight back to the account you logged in with (Administrator, usually), from any page
	const BACK_SHORTCUT_LABEL = "Ctrl+Shift+A";
	const is_back_shortcut = (e) => (e.ctrlKey || e.metaKey) && e.shiftKey && !e.altKey && e.code === "KeyA";

	// Browsers ignore autocomplete="off" on name/email fields and offer saved addresses. These fields
	// are for made-up test users, so: no name attribute, no type=email, and a token that turns
	// Chrome's suggestions off, plus the opt-outs password managers read.
	const NO_AUTOFILL = 'autocomplete="one-time-code" spellcheck="false" data-lpignore="true" data-1p-ignore data-bwignore data-form-type="other"';

	const ICONS = {
		swap: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 4 3 8l4 4"/><path d="M3 8h14"/><path d="m17 20 4-4-4-4"/><path d="M21 16H7"/></svg>`,
		search: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>`,
		back: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 14 4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/></svg>`,
		close: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>`,
		enter: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 4v7a4 4 0 0 1-4 4H4"/><path d="m9 10-5 5 5 5"/></svg>`,
		star: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/></svg>`,
		plus: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>`,
		grip: `<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="9" cy="6" r="1.6"/><circle cx="15" cy="6" r="1.6"/><circle cx="9" cy="12" r="1.6"/><circle cx="15" cy="12" r="1.6"/><circle cx="9" cy="18" r="1.6"/><circle cx="15" cy="18" r="1.6"/></svg>`,
		chevron_right: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>`,
		chevron_left: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>`,
		shield: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 4 6v6c0 4.5 3.4 8 8 9 4.6-1 8-4.5 8-9V6z"/><path d="m9 12 2 2 4-4"/></svg>`,
		info: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 7.5h.01"/></svg>`,
		key: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="15" r="4"/><path d="m10.8 12.2 9.2-9.2"/><path d="m17 6 3 3"/><path d="m14 9 2 2"/></svg>`,
		lock: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>`,
		user_plus: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="10" cy="8" r="4"/><path d="M2 21a8 8 0 0 1 16 0M19 8v6M16 11h6"/></svg>`,
		eye: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>`,
	};

	// ---------- helpers ----------

	function on_ready(fn) {
		if (document.readyState === "loading") {
			document.addEventListener("DOMContentLoaded", fn);
		} else {
			fn();
		}
	}

	function current_user() {
		return (frappe.session && frappe.session.user) || frappe.get_cookie?.("user_id") || "Guest";
	}

	function t(msg, args) {
		return window.__ ? __(msg, args) : msg.replace(/\{(\d+)\}/g, (_, i) => args[i]);
	}

	function esc(s) {
		return frappe.utils?.escape_html ? frappe.utils.escape_html(s || "") : $("<div>").text(s || "").html();
	}

	function storage(store, key, value) {
		try {
			if (value === undefined) return store.getItem(key);
			if (value === null) store.removeItem(key);
			else store.setItem(key, value);
		} catch (e) {}
		return null;
	}

	function read_json(store, key, fallback) {
		try {
			return JSON.parse(storage(store, key) || "null") ?? fallback;
		} catch (e) {
			return fallback;
		}
	}

	function hue(str) {
		let h = 0;
		for (const ch of str || "") h = (h * 31 + ch.charCodeAt(0)) % 360;
		return h;
	}

	function initials(u) {
		const label = u.full_name || u.name || "?";
		const parts = label
			.replace(/([a-z])([A-Z])/g, "$1 $2") // "JaneSmith" -> "Jane Smith"
			.split(/[\s@._-]+/)
			.filter(Boolean);
		return ((parts[0]?.[0] || "") + (parts[1]?.[0] || "")).toUpperCase() || "?";
	}

	function avatar(u, cls = "") {
		// Initials sit underneath; a broken image removes itself and reveals them
		const img = u.user_image ? `<img src="${esc(u.user_image)}" alt="" onerror="this.remove()">` : "";
		return `<span class="us-avatar ${cls}" style="--us-hue:${hue(u.name)}">${esc(initials(u))}${img}</span>`;
	}

	function display_name(u) {
		return u?.full_name || u?.name || "";
	}

	// Frappe-style search: 0 = no match, lower = better. Typed words may match the starts of words in
	// any order ("inv sal" → Sales Invoice), the letters may spell the initials ("si" → Sales Invoice),
	// and a plain "contains" still matches, ranked last.
	function match_rank(text, query) {
		const q = (query || "").trim().toLowerCase();
		if (!q) return 1;
		const t = (text || "").toLowerCase();
		const words = t.split(/[\s._\-/]+/).filter(Boolean);
		const parts = q.split(/\s+/);
		if (t === q) return 1;
		if (t.startsWith(q)) return 2;
		if (parts.length === 1 && q.length > 1 && words.map((w) => w[0]).join("").startsWith(q)) return 3;
		if (parts.every((p) => words.some((w) => w.startsWith(p)))) return 4;
		if (t.includes(q)) return 5;
		return 0;
	}

	// Filter and order a list by match_rank, keeping the original order among equal matches
	function search(list, query, text = (x) => x) {
		if (!(query || "").trim()) return list;
		return list
			.map((item, i) => ({ item, i, rank: match_rank(text(item), query) }))
			.filter((x) => x.rank)
			.sort((a, b) => a.rank - b.rank || a.i - b.i)
			.map((x) => x.item);
	}

	// Bold the typed words where they start a word (or the whole query where it appears)
	function mark_match(text, query) {
		const parts = (query || "").trim().toLowerCase().split(/\s+/).filter(Boolean);
		if (!parts.length) return esc(text);
		const lower = text.toLowerCase();
		const hits = new Array(text.length).fill(false);
		for (const p of parts) {
			let at = -1;
			for (let i = lower.indexOf(p); i !== -1; i = lower.indexOf(p, i + 1)) {
				if (i === 0 || /[\s._\-/]/.test(lower[i - 1])) { at = i; break; }
			}
			if (at === -1) at = lower.indexOf(p);
			for (let k = at; at !== -1 && k < at + p.length; k++) hits[k] = true;
		}
		let out = "";
		for (let i = 0; i < text.length; i++) {
			const open = hits[i] && !hits[i - 1];
			const shut = hits[i] && !hits[i + 1];
			out += (open ? "<b>" : "") + esc(text[i]) + (shut ? "</b>" : "");
		}
		return out;
	}

	function slug(s) {
		return (s || "")
			.toLowerCase()
			.normalize("NFKD")
			.replace(/[^\w\s.-]/g, "")
			.trim()
			.replace(/[\s_]+/g, ".");
	}

	// ---------- identity (known before any API call) ----------

	const who = {
		// The account that actually logged in; usage + pins are stored per real user.
		real: frappe.boot?.user?.impersonated_by || current_user(),
		is_switched: !!frappe.boot?.user?.impersonated_by,
	};

	function boot_user_info(name) {
		const info = frappe.user_info?.(name);
		return { name, full_name: info?.fullname || name, user_image: info?.image || null };
	}

	// ---------- usage + pins (per real user, in this browser) ----------

	const store = {
		usage_key: () => `${USAGE_KEY}:${who.real}`,
		pins_key: () => `${PINS_KEY}:${who.real}`,

		// { [user]: { count, last, info } }
		usage() {
			const usage = read_json(localStorage, this.usage_key(), null);
			if (usage) return usage;
			// Seed from the old "recent" list so existing history isn't lost
			const legacy = read_json(localStorage, `${LEGACY_RECENT_KEY}:${who.real}`, []);
			return Object.fromEntries(legacy.map((info, i) => [info.name, { count: 1, last: -i, info }]));
		},

		remember(u) {
			if (!u?.name || u.name === who.real) return;
			const usage = this.usage();
			usage[u.name] = { count: (usage[u.name]?.count || 0) + 1, last: Date.now(), info: slim(u, usage[u.name]?.info) };
			storage(localStorage, this.usage_key(), JSON.stringify(usage));
		},

		// [info, ...] in the order they were pinned
		pins() {
			return read_json(localStorage, this.pins_key(), []);
		},

		is_pinned(name) {
			return this.pins().some((p) => p.name === name);
		},

		// Save the new order of the pins that are on screen; pins hidden by the current filter keep their slots
		reorder_pins(names) {
			const pins = this.pins();
			const by_name = Object.fromEntries(pins.map((p) => [p.name, p]));
			const queue = names.filter((n) => by_name[n]);
			const shown = new Set(queue);
			const ordered = pins.map((p) => (shown.has(p.name) ? by_name[queue.shift()] : p));
			storage(localStorage, this.pins_key(), JSON.stringify(ordered));
		},

		// Forget deleted or disabled users that are still cached in this browser
		forget(names) {
			const gone = new Set(names);
			if (!gone.size) return;
			const usage = this.usage();
			Object.keys(usage).forEach((n) => gone.has(n) && delete usage[n]);
			storage(localStorage, this.usage_key(), JSON.stringify(usage));
			const pins = this.pins().filter((p) => !gone.has(p.name));
			storage(localStorage, this.pins_key(), JSON.stringify(pins));
		},

		cached_names() {
			return [...new Set([...Object.keys(this.usage()), ...this.pins().map((p) => p.name)])];
		},

		toggle_pin(u) {
			let pins = this.pins();
			if (pins.some((p) => p.name === u.name)) pins = pins.filter((p) => p.name !== u.name);
			else pins.push(slim(u));
			storage(localStorage, this.pins_key(), JSON.stringify(pins));
		},
	};

	function slim(u, fallback = {}) {
		const pick = (k) => u[k] ?? fallback[k] ?? null;
		return {
			name: u.name,
			full_name: pick("full_name"),
			user_image: pick("user_image"),
			user_type: pick("user_type"),
			roles: pick("roles") || [],
		};
	}

	// ---------- switching (shared by the widget and the banner) ----------

	function switch_to(user, { back = false, to = null } = {}) {
		$("#us-floating-container").removeClass("us-open").addClass("us-busy");
		frappe.dom?.freeze?.(t("Switching to {0}...", [esc(display_name(user))]));
		return frappe
			.call({
				method: back ? `${API}.switch_back` : `${API}.switch_to_user`,
				args: back ? {} : { target_user: user.name },
				type: "POST",
			})
			.then(() => {
				if (!back) store.remember(user);
				// sessionStorage caches are per-user; drop them before the new user's page loads
				try {
					Object.keys(sessionStorage)
						.filter((k) => k.startsWith(CACHE_KEY) || k.startsWith(BANNER_KEY))
						.forEach((k) => sessionStorage.removeItem(k));
				} catch (e) {}
				if (to) window.location.href = to;
				// The current desk route may not be accessible to the new user, so restart from /app
				else if (window.location.pathname === "/app") window.location.reload();
				else if (window.location.pathname.startsWith("/app") || window.location.pathname.startsWith("/desk")) window.location.href = "/app";
				else window.location.reload();
			})
			.catch(() => {
				$("#us-floating-container").removeClass("us-busy");
				frappe.dom?.unfreeze?.();
			});
	}

	function switch_back() {
		return switch_to({ name: who.real, full_name: who.real_full_name || who.real }, { back: true });
	}

	// ---------- "you are switched" banner ----------

	function render_banner(me, real) {
		$("#us-banner").remove();
		if (!who.is_switched) return;

		const collapsed = storage(sessionStorage, BANNER_KEY) === "1";
		const $banner = $(`
			<div id="us-banner" class="${collapsed ? "us-banner--collapsed" : ""}" role="status">
				<div class="us-banner-frame"></div>
				<div class="us-banner-pill">
					<span class="us-banner-icon">${ICONS.eye}</span>
					<span class="us-banner-text">${t("Viewing as {0}", [`<b>${esc(display_name(me))}</b>`])}</span>
					<button class="us-banner-back" title="${t("Switch back ({0})", [BACK_SHORTCUT_LABEL])}">
						${ICONS.back}<span>${t("Back to {0}", [esc(display_name(real))])}</span>
					</button>
					<button class="us-banner-collapse" title="${t("Collapse")}" aria-label="${t("Collapse")}">${ICONS.close}</button>
				</div>
			</div>
		`).appendTo("body");

		$banner.find(".us-banner-back").on("click", switch_back);
		$banner.find(".us-banner-collapse").on("click", (e) => {
			e.stopPropagation();
			$banner.addClass("us-banner--collapsed");
			storage(sessionStorage, BANNER_KEY, "1");
		});
		// Collapsed, it's just the icon; click to expand again
		$banner.find(".us-banner-pill").on("click", () => {
			if (!$banner.hasClass("us-banner--collapsed")) return;
			$banner.removeClass("us-banner--collapsed");
			storage(sessionStorage, BANNER_KEY, null);
		});
	}

	// ---------- permission probe ----------

	// Decide whether to show the button without hitting the server on every page load.
	function check_allowed() {
		if (frappe.boot && "user_switcher_allowed" in frappe.boot) {
			return Promise.resolve(!!frappe.boot.user_switcher_allowed);
		}
		const key = `${CACHE_KEY}:${current_user()}`;
		const cached = storage(sessionStorage, key);
		if (cached !== null) return Promise.resolve(cached === "1");

		return frappe
			.call({ method: `${API}.get_context`, args: { limit: 0 }, type: "GET" })
			.then((r) => {
				const allowed = !!r.message?.allowed;
				storage(sessionStorage, key, allowed ? "1" : "0");
				return allowed;
			})
			.catch(() => false);
	}

	// ---------- the widget ----------

	// ---------- "How to use" guide (shown from the (i) button next to Hide) ----------

	function info_html() {
		const kbd = (k) => `<kbd>${k}</kbd>`;
		const item = (icon, title, text) =>
			`<div class="us-info-item"><span class="us-info-icon">${ICONS[icon]}</span><div><b>${title}</b><p>${text}</p></div></div>`;
		return `
			<p class="us-info-lead">${t("See the app exactly as another user sees it. Pick a user and you are logged in as them. Go back anytime with one click.")}</p>
			${item("swap", t("Switch to a user"), t("Click a user, or press its number {0} to {1}. Type in the search box to find someone by name or email.", [kbd(1), kbd(9)]))}
			${item("back", t("Come back to your own account"), t("Press {0}, click “Back to …” at the top, or press {1} on any page. Inside a screen, the ‹ arrow next to the picture, Esc, or Backspace (when you are not typing) returns to the list.", [kbd(0), kbd(BACK_SHORTCUT_LABEL)]))}
			${item("star", t("Pinned users"), t("Click the star on a user to pin them at the top. Pinned users keep their numbers, even after you switch. Drag a pinned user up or down to change the order. Users you switch to often also show under Most used."))}
			${item("shield", t("Manage roles"), t("Click Manage roles to give or remove roles (access) for the user you are viewing as. Tick the roles, then press Save roles."))}
			${item("key", t("Doctype access"), t("Click Doctype access to choose which roles can read, write, create or submit a doctype. The roles of the user you are viewing as come first, so one click gives them what they are missing. When a page says Not permitted while you are switched, use Fix access in the message."))}
			${item("plus", t("Create a test user"), t("Click New test user, type a name, then tick the roles or pick a role profile to tick its roles at once. You can switch into the new user right away."))}
			${item("eye", t("Hide the button"), t("Click Hide to remove the button until your next login. Press {0} to bring it back.", [kbd(SHORTCUT_LABEL)]))}
			<div class="us-info-keys">
				<span>${kbd(SHORTCUT_LABEL)} ${t("open or close")}</span>
				<span>${kbd("↑")}${kbd("↓")}${kbd("↵")} ${t("move and pick")}</span>
				<span>${kbd("Esc")} ${t("close")}</span>
			</div>
			${item("info", t("Good to know"), t("It works only when developer mode and user_switcher_enabled are both on. Every switch is saved in the User Switch Log. Do not use it on a live site."))}
		`;
	}

	function render_widget() {
		if ($("#us-floating-container").length) return;

		const $root = $(`
			<div id="us-floating-container" role="region" aria-label="${t("User Switcher")}">
				<div class="us-card" role="dialog" aria-label="${t("Switch user")}" aria-hidden="true">
					<div class="us-identity"></div>

					<div class="us-browse">
						<div class="us-tiles">
							<button type="button" class="us-tile us-tile-roles">${ICONS.shield}<span>${t("Manage roles")}</span></button>
							<button type="button" class="us-tile us-tile-access">${ICONS.lock}<span>${t("Doctype access")}</span></button>
							<button type="button" class="us-tile us-new">${ICONS.user_plus}<span>${t("New test user")}</span></button>
						</div>
						<div class="us-search">
							<span class="us-search-icon">${ICONS.search}</span>
							<input type="text" placeholder="${t("Search name or email")}" autocomplete="off" spellcheck="false">
							<kbd class="us-kbd">${SHORTCUT_LABEL}</kbd>
						</div>
						<div class="us-filters" role="tablist">
							<button class="us-filter active" data-type="">${t("All")}</button>
							<button class="us-filter" data-type="System User">${t("System")}</button>
							<button class="us-filter" data-type="Website User">${t("Website")}</button>
						</div>
						<div class="us-list" role="listbox"></div>
					</div>

					<form class="us-create" autocomplete="off" novalidate>
						<div class="us-create-head">
							<span class="us-create-titles">
								<span class="us-create-title">${t("New test user")}</span>
								<span class="us-create-sub"></span>
							</span>
						</div>
						<div class="us-create-grid us-create-fields">
							<label class="us-field">
								<span>${t("Full name")}</span>
								<input class="us-new-name" type="text" placeholder="${t("e.g. Priya Accounts")}" ${NO_AUTOFILL}>
							</label>
							<label class="us-field">
								<span>${t("Email")}</span>
								<input class="us-new-email" type="text" inputmode="email" placeholder="name@example.com" ${NO_AUTOFILL}>
							</label>
						</div>
						<div class="us-field us-profiles" hidden>
							<span>${t("Role profiles")}</span>
							<div class="us-profile-strip" role="group" aria-label="${t("Role profiles")}"></div>
						</div>
						<div class="us-field us-roles-field">
							<span class="us-field-row">
								<span>${t("Roles")}</span>
								<span class="us-picked-count"></span>
							</span>
							<input class="us-role-search" type="text" placeholder="${t("Filter roles")}">
								<div class="us-role-list"><div class="us-empty">${t("Loading roles...")}</div></div>
						</div>
						<div class="us-create-actions">
							<span class="us-form-status"></span>
							<button type="button" class="us-btn us-create-only">${t("Create")}</button>
							<button type="submit" class="us-btn us-btn--primary">${t("Create & switch")}</button>
							<button type="button" class="us-btn us-roles-cancel">${t("Cancel")}</button>
							<button type="button" class="us-btn us-btn--primary us-roles-save">${t("Save roles")}</button>
						</div>
					</form>

					<div class="us-info">
						<div class="us-create-head">
							<span class="us-create-titles"><span class="us-create-title">${t("How to use User Switcher")}</span></span>
						</div>
						${info_html()}
					</div>

					<div class="us-access">
						<div class="us-create-head">
							<span class="us-create-titles">
								<span class="us-create-title">${t("Doctype access")}</span>
								<span class="us-access-sub">${t("Choose which roles can open and change a doctype")}</span>
							</span>
						</div>
						<label class="us-field">
							<span>${t("DocType")}</span>
							<span class="us-combo">
								<input class="us-access-doctype" type="text" role="combobox" aria-expanded="false" aria-controls="us-access-options"
									aria-autocomplete="list" placeholder="${t("Type to search, e.g. Sales Invoice")}" ${NO_AUTOFILL}>
								<span class="us-combo-list" id="us-access-options" role="listbox" hidden></span>
							</span>
						</label>
						<div class="us-access-summary"></div>
						<div class="us-access-tools">
							<span class="us-access-search">
								${ICONS.search}
								<input class="us-access-role-search" type="text" placeholder="${t("Search roles or add one")}" autocomplete="off" spellcheck="false">
							</span>
							<label class="us-access-more"><input type="checkbox"> ${t("All rights")}</label>
						</div>
						<div class="us-access-suggest"></div>
						<div class="us-access-roles"></div>
						<div class="us-create-actions us-access-actions">
							<span class="us-access-foot">
								<span class="us-access-changes"></span>
								<a class="us-access-advanced" href="/app/permission-manager"
									title="${t("Field-level and “only if creator” rules are set there")}">${t("Role Permission Manager")} ↗</a>
							</span>
							<button type="button" class="us-btn us-access-cancel">${t("Cancel")}</button>
							<button type="button" class="us-btn us-btn--primary us-access-save" disabled>${t("Save")}</button>
						</div>
					</div>

					<div class="us-footer">
						<span class="us-hints">
							<span>${t("Press a number to switch")}</span>
							<span class="us-hint-back" title="${t("{0} from any page", [BACK_SHORTCUT_LABEL])}">· ${t("{0} to go back", ["<b>0</b>"])}</span>
						</span>
						<span class="us-footer-actions">
							<button class="us-info-btn" title="${t("How to use")}" aria-label="${t("How to use")}" aria-pressed="false">${ICONS.info}</button>
							<button class="us-hide" title="${t("Hide until next session ({0} to reopen)", [SHORTCUT_LABEL])}">${t("Hide")}</button>
						</span>
					</div>
				</div>
				<button class="us-trigger" aria-label="${t("Switch user")}" aria-expanded="false">
					<span class="us-trigger-avatar"></span>
					<span class="us-trigger-label"></span>
					<span class="us-trigger-badge">${ICONS.swap}</span>
				</button>
			</div>
		`).appendTo("body");

		const $card = $root.find(".us-card");
		const $trigger = $root.find(".us-trigger");
		const $list = $root.find(".us-list");
		const $identity = $root.find(".us-identity");
		const $search = $root.find(".us-search input");
		const $create = $root.find(".us-create");
		const state = { ctx: null, user_type: "", txt: "", request_id: 0, creating: false, info: false, editing: null, roles: null, picked: new Set(), access: null };
		let search_timer;

		if (storage(sessionStorage, HIDDEN_KEY) === "1") $root.addClass("us-hidden");

		// Paint the trigger straight away from what we already know, then refine once loaded.
		paint_trigger({ current_user: boot_user_info(current_user()), is_switched: who.is_switched });
		// Website pages have no boot info to tell us if we're switched, so ask once up front
		if (!frappe.boot?.user) fetch_users();

		const is_open = () => $root.hasClass("us-open");

		function open() {
			$root.removeClass("us-hidden").addClass("us-open");
			storage(sessionStorage, HIDDEN_KEY, null);
			$card.attr("aria-hidden", "false");
			$trigger.attr("aria-expanded", "true");
			fetch_users();
			if (!state.creating && !state.access) setTimeout(() => $search.trigger("focus").trigger("select"), 60);
		}

		function show_info(on) {
			if (on && state.creating) show_create(false);
			if (on && state.access) show_access(false);
			state.info = on;
			$root.toggleClass("us-info-mode", on);
			$root.find(".us-info-btn").toggleClass("is-on", on).attr("aria-pressed", on);
			if (on) $root.find(".us-info").scrollTop(0);
			else $search.trigger("focus");
		}

		$root.find(".us-info-btn").on("click", () => show_info(!state.info));
		$root.find(".us-tile-roles").on("click", () => state.ctx && show_roles(state.ctx.current_user));
		$root.find(".us-tile-access").on("click", () => show_access(true, route_doctype()));

		// Leave whichever sub-screen is open and return to the user list
		function go_back() {
			if (state.info) show_info(false);
			else if (state.access) show_access(false);
			else if (state.creating) show_create(false);
		}

		function close() {
			state.info = false;
			$root.removeClass("us-open us-info-mode").find(".us-info-btn").removeClass("is-on").attr("aria-pressed", false);
			$card.attr("aria-hidden", "true");
			$trigger.attr("aria-expanded", "false");
		}

		$trigger.on("click", (e) => {
			e.stopPropagation();
			is_open() ? close() : open();
		});

		$root.find(".us-hide").on("click", () => {
			close();
			$root.addClass("us-hidden");
			storage(sessionStorage, HIDDEN_KEY, "1");
			frappe.show_alert?.({
				message: t("User Switcher hidden. Press {0} to bring it back.", [SHORTCUT_LABEL]),
				indicator: "blue",
			});
		});

		$(document).on("click.user_switcher", (e) => {
			// A click that re-rendered its own target (e.g. a right button) leaves it detached; that was inside
			if (!e.target.isConnected) return;
			if (is_open() && !$(e.target).closest("#us-floating-container").length) close();
		});

		$(document).on("keydown.user_switcher", (e) => {
			if (is_open_shortcut(e)) {
				e.preventDefault();
				e.stopPropagation();
				is_open() ? close() : open();
				return;
			}
			if (!is_open()) return;

			if (e.key === "Escape") {
				if (state.info || state.access || state.creating) go_back();
				else {
					close();
					$trigger.trigger("focus");
				}
				return;
			}
			// Backspace also goes back, but never while typing: deleting text must not throw away a half-filled form
			const typing = $(e.target).is("input:not([type=checkbox]):not([type=radio]), textarea, select, [contenteditable]");
			if (e.key === "Backspace" && !typing && (state.info || state.access || state.creating)) {
				e.preventDefault();
				go_back();
				return;
			}
			if (state.creating || state.info || state.access) return; // let the form have every other key

			// 1-9 switch to the numbered user, 0 goes back. Only while the search box is
			// empty, so digits can still be typed to search once a query is started.
			const digit = /^Digit(\d)$/.exec(e.code)?.[1] ?? (/^\d$/.test(e.key) ? e.key : null);
			if (digit !== null && !e.ctrlKey && !e.metaKey && !e.altKey && !$search.val()) {
				e.preventDefault();
				if (digit === "0") {
					if (who.is_switched) switch_back();
				} else {
					$list.find(`.us-item[data-index="${digit}"]`).trigger("click");
				}
				return;
			}

			if (e.key === "ArrowDown" || e.key === "ArrowUp") {
				e.preventDefault();
				move_active(e.key === "ArrowDown" ? 1 : -1);
			} else if (e.key === "Enter" && $(e.target).is($search)) {
				e.preventDefault();
				$list.find(".us-item.is-active").trigger("click");
			}
		});

		$search.on("input", () => {
			clearTimeout(search_timer);
			search_timer = setTimeout(() => {
				state.txt = $search.val().trim();
				fetch_users();
			}, 200);
		});

		$root.find(".us-filter").on("click", function () {
			$root.find(".us-filter").removeClass("active");
			$(this).addClass("active");
			state.user_type = $(this).data("type") || "";
			fetch_users();
			$search.trigger("focus");
		});

		// ---------- drag to reorder pinned users ----------

		// Rows swap live while you drag: note where every pinned row is (FLIP), move the dragged row
		// in the DOM, then slide each row from its old spot to the new one. The order is saved on drop;
		// releasing outside the list cancels and puts everything back.
		const reduced_motion = !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
		const pinned_rows = () => $list.find(".us-item[draggable=true]").toArray();

		function renumber(rows) {
			rows.forEach((row, i) => {
				row.dataset.index = i + 1;
				const $num = $(row).find("kbd.us-num");
				if (i < 9) $num.text(i + 1);
			});
		}

		function move_dragged(client_y) {
			const rows = pinned_rows();
			const dragged = rows.find((r) => r.dataset.name === state.drag_name);
			if (!dragged) return;

			// Layout offsets ignore in-flight slide transforms, so a row mid-slide can't flip the choice back
			const y = client_y - $list[0].getBoundingClientRect().top + $list[0].scrollTop;
			const others = rows.filter((r) => r !== dragged);
			const before = others.find((r) => y < r.offsetTop + r.offsetHeight / 2);
			const last = others[others.length - 1];
			if (before ? dragged.nextElementSibling === before : !last || last.nextElementSibling === dragged) return;

			const first_top = new Map(rows.map((r) => [r, r.getBoundingClientRect().top]));
			before ? before.before(dragged) : last.after(dragged);

			rows.forEach((r) => r.getAnimations().forEach((a) => a.id === "us-swap" && a.cancel()));
			const after_rows = pinned_rows();
			renumber(after_rows);
			if (reduced_motion) return;
			after_rows.forEach((r) => {
				const dy = first_top.get(r) - r.getBoundingClientRect().top;
				if (!dy) return;
				r.animate([{ transform: `translateY(${dy}px)` }, { transform: "none" }], {
					id: "us-swap",
					duration: 240,
					easing: "cubic-bezier(0.2, 0.9, 0.3, 1)",
				});
			});
		}

		function finish_drag() {
			const moved = state.drag_name;
			const names = pinned_rows().map((r) => r.dataset.name);
			if (state.dropped) store.reorder_pins(names);
			const saved = state.dropped;
			state.drag_name = null;
			state.dropped = false;
			paint_list(); // rebuilds rows from the saved order (or the old one, if cancelled)
			if (saved) {
				$list.find(`.us-item[data-name="${CSS.escape(moved)}"]`)
					.addClass("us-settled")
					.one("animationend", function () {
						$(this).removeClass("us-settled");
					});
			}
		}

		// The whole card accepts the drag, and dragenter must be accepted too: the browser picks the
		// cursor from dragenter, so accepting only dragover on the list flashes the red "no drop" sign
		// every time the pointer crosses into another element (or sits over the search box, header, footer).
		// Releasing outside the card still cancels.
		$card
			.on("dragenter dragover", (e) => {
				if (!state.drag_name) return;
				e.preventDefault();
				e.originalEvent.dataTransfer.dropEffect = "move";
				if (e.type === "dragover") move_dragged(e.originalEvent.clientY);
			})
			.on("drop", (e) => {
				if (!state.drag_name) return;
				e.preventDefault();
				move_dragged(e.originalEvent.clientY); // settle exactly where the pointer was released
				state.dropped = true;
			});

		function fetch_users() {
			const request_id = ++state.request_id;
			if (!state.ctx) $list.html(skeleton());

			return frappe
				.call({
					method: `${API}.get_context`,
					args: { txt: state.txt, user_type: state.user_type, cached: JSON.stringify(store.cached_names()) },
					type: "GET",
				})
				.then((r) => {
					if (request_id !== state.request_id) return; // a newer search is in flight
					const ctx = r.message || {};
					if (!ctx.allowed) {
						$list.html(empty_state(t("You are not permitted to switch users.")));
						return;
					}
					store.forget(ctx.stale || []);
					state.ctx = ctx;
					who.real = ctx.real_user.name;
					who.real_full_name = display_name(ctx.real_user);
					who.is_switched = !!ctx.is_switched;
					paint_trigger(ctx);
					paint_identity(ctx);
					paint_list();
					render_banner(ctx.current_user, ctx.real_user);
				});
		}

		function paint_trigger(ctx) {
			const me = ctx.current_user;
			$root.toggleClass("us-switched", !!ctx.is_switched);
			$trigger.find(".us-trigger-avatar").html(avatar(me, "us-avatar--lg"));
			$trigger
				.find(".us-trigger-label")
				.html(ctx.is_switched ? `${t("Viewing as")} <b>${esc(display_name(me))}</b>` : t("Switch user"));
		}

		function paint_identity(ctx) {
			const me = ctx.current_user;
			const real = ctx.real_user;
			$identity.html(`
				<div class="us-identity-main">
					<button class="us-icon-btn us-head-back" aria-label="${t("Back")}" title="${t("Back (Esc)")}">${ICONS.chevron_left}</button>
					${avatar(me, "us-avatar--lg")}
					<div class="us-identity-text">
						<span class="us-eyebrow">${ctx.is_switched ? t("Viewing as") : t("Signed in as")}</span>
						<span class="us-identity-name" title="${esc(me.name)}">${esc(display_name(me))}</span>
					</div>
					${
						ctx.is_switched
							? `<button class="us-switch-back" title="${t("Back to {0} ({1} from any page)", [esc(display_name(real)), BACK_SHORTCUT_LABEL])}">
								${ICONS.back}<span class="us-switch-back-text">${t("Back to {0}", [esc(display_name(real))])}</span><kbd>0</kbd>
							</button>`
							: ""
					}
					<button class="us-icon-btn us-close" aria-label="${t("Close")}">${ICONS.close}</button>
				</div>
			`);
			// Administrator's roles can't be edited (the server refuses), so don't offer it
			$root.find(".us-tile-roles").prop("hidden", me.name === "Administrator");
			$root.find(".us-tile-access").attr("title", route_doctype() ? t("Who can open and change {0}", [route_doctype()]) : t("Give a role access to a doctype"));
			$identity.find(".us-close").on("click", close);
			$identity.find(".us-head-back").on("click", go_back);
			$identity.find(".us-switch-back").on("click", switch_back);
		}

		// Pinned first (stable numbers), then most used, then everyone else.
		function paint_list() {
			const ctx = state.ctx;
			if (!ctx) return;
			const skip = new Set([ctx.current_user.name, ctx.real_user.name]);
			// Cached entries may be stale; prefer the live row where the server returned one
			const live = Object.fromEntries(ctx.users.map((u) => [u.name, u]));
			const fresh = (u) => live[u.name] || u;
			const matches_type = (u) => !state.user_type || u.user_type === state.user_type;

			let pinned = [];
			let most_used = [];
			if (!state.txt) {
				pinned = store
					.pins()
					.map(fresh)
					.filter(matches_type); // never skipped, even the user you are viewing as, so pinned numbers stay put
				const pinned_names = new Set(pinned.map((u) => u.name));
				most_used = Object.values(store.usage())
					.filter((e) => !skip.has(e.info.name) && !pinned_names.has(e.info.name))
					.map((e) => ({ ...e, info: fresh(e.info) }))
					.filter((e) => matches_type(e.info))
					.sort((a, b) => b.count - a.count || b.last - a.last)
					.slice(0, MAX_MOST_USED);
			}
			const shown = new Set([...pinned.map((u) => u.name), ...most_used.map((e) => e.info.name)]);
			const others = ctx.users.filter((u) => !shown.has(u.name));

			const active_name = $list.find(".us-item.is-active").data("name");
			$root.toggleClass("us-can-go-back", !!ctx.is_switched);
			$list.empty();

			if (!pinned.length && !most_used.length && !others.length) {
				$list.html(
					empty_state(state.txt ? t("No users match “{0}”", [esc(state.txt)]) : t("No other users found"))
				);
				return;
			}

			let index = 0;
			const section = (title, rows) => {
				if (!rows.length) return;
				if (pinned.length || most_used.length) $list.append(`<div class="us-group">${title}</div>`);
				rows.forEach(({ u, uses, drag }) =>
					$list.append(item(u, ++index, uses, drag, u.name === ctx.current_user.name))
				);
			};
			section(t("Pinned"), pinned.map((u) => ({ u, drag: pinned.length > 1 })));
			section(t("Most used"), most_used.map((e) => ({ u: e.info, uses: e.count })));
			section(t("All users"), others.map((u) => ({ u })));

			const $active = active_name ? $list.find(`.us-item[data-name="${CSS.escape(active_name)}"]`) : $();
			($active.length ? $active : $list.find(".us-item").first()).addClass("is-active");
		}

		function item(u, index, uses, drag, current) {
			const website = u.user_type === "Website User" ? `<span class="us-chip us-chip--web">${t("Website")}</span>` : "";
			const now = current ? `<span class="us-chip us-chip--current">${t("Current")}</span>` : "";
			const key = index <= 9 ? `<kbd class="us-num">${index}</kbd>` : `<span class="us-num us-num--none"></span>`;
			const pinned = store.is_pinned(u.name);
			const title = uses ? t("Switched {0} times", [uses]) : "";
			const $item = $(`
				<div class="us-item" role="option" tabindex="-1" title="${esc(drag ? [title, t("Drag to reorder")].filter(Boolean).join(" · ") : title)}">
					${avatar(u)}
					<div class="us-item-text">
						<span class="us-item-name"><span class="us-item-name-text">${esc(display_name(u))}</span>${now}${website}</span>
						<span class="us-item-email">${esc(u.name)}</span>
					</div>
					<button class="us-pin ${pinned ? "is-pinned" : ""}" title="${pinned ? t("Unpin") : t("Pin to top")}"
						aria-label="${pinned ? t("Unpin") : t("Pin to top")}" aria-pressed="${pinned}">${ICONS.star}</button>
					${key}
				</div>
			`)
				.attr({ "data-index": index, "data-name": u.name })
				.on("mouseenter", function () {
					$list.find(".us-item").removeClass("is-active");
					$(this).addClass("is-active");
				})
				.toggleClass("us-item--current", !!current)
				// Already viewing as this user: nothing to switch, just keep its numbered slot
				.on("click", () => (current ? close() : switch_to(u)));

			$item.find(".us-pin").on("click", (e) => {
				e.stopPropagation();
				store.toggle_pin(u);
				paint_list();
			});

			if (drag) {
				$item
					.attr("draggable", "true")
					.on("dragstart", (e) => {
						state.drag_name = u.name;
						state.dropped = false;
						e.originalEvent.dataTransfer.effectAllowed = "move";
						e.originalEvent.dataTransfer.setData("text/plain", u.name);
						// A tick later, so the browser snapshots the normal-looking row as the drag image
						setTimeout(() => $item.addClass("is-dragging"));
					})
					.on("dragend", finish_drag);
			}
			return $item;
		}

		function move_active(step) {
			const $items = $list.find(".us-item");
			if (!$items.length) return;
			let idx = $items.index($items.filter(".is-active"));
			idx = (idx + step + $items.length) % $items.length;
			$items.removeClass("is-active");
			$items.eq(idx).addClass("is-active")[0].scrollIntoView({ block: "nearest" });
		}

		function skeleton() {
			return Array.from({ length: 4 })
				.map(
					() => `<div class="us-item us-skeleton">
						<span class="us-avatar"></span>
						<div class="us-item-text"><span class="us-bar"></span><span class="us-bar us-bar--short"></span></div>
					</div>`
				)
				.join("");
		}

		function empty_state(msg) {
			return `<div class="us-empty">${msg}</div>`;
		}

		// ---------- create test user ----------

		const $name = $create.find(".us-new-name");
		const $email = $create.find(".us-new-email");
		const $role_search = $create.find(".us-role-search");
		const $role_list = $create.find(".us-role-list");
		let email_touched = false;

		$root.find(".us-new").on("click", () => show_create(true));

		function show_create(on) {
			if (on && state.access) show_access(false);
			state.creating = on;
			state.editing = null;
			if (on && state.info) show_info(false);
			$root.toggleClass("us-creating", on).removeClass("us-roles-mode");
			$create.find(".us-create-title").text(t("New test user"));
			$create.find(".us-create-sub").text(t("Create a user, then switch into it. No email is sent."));
			if (!on) {
				$search.trigger("focus");
				return;
			}
			const seed = state.txt && !state.txt.includes("@") ? state.txt : "";
			$create[0].reset();
			state.picked = new Set();
			email_touched = false;
			$name.val(seed).trigger("input");
			setTimeout(() => $name.trigger("focus"), 30);
			load_roles();
			load_profiles();
		}

		// ---------- role profiles: one click ticks a profile's roles ----------

		const $profiles = $create.find(".us-profiles");
		const $profile_strip = $create.find(".us-profile-strip");

		function load_profiles() {
			if (state.profiles) return paint_profiles();
			frappe.call({ method: `${API}.get_role_profiles`, type: "GET" }).then((r) => {
				state.profiles = r.message || [];
				paint_profiles();
			});
		}

		// A profile is "on" while the ticked roles are exactly its roles
		const profile_matches = (p) => p.roles.length === state.picked.size && p.roles.every((r) => state.picked.has(r));

		function paint_profiles() {
			const list = state.profiles || [];
			$profiles.prop("hidden", !list.length || !!state.editing);
			$profile_strip.html(
				list
					.map((p, i) => `<button type="button" class="us-profile ${profile_matches(p) ? "is-on" : ""}" data-i="${i}"
						aria-pressed="${profile_matches(p)}" title="${esc(p.roles.join(", "))}">
						<span>${esc(p.name)}</span><span class="us-profile-count">${p.roles.length}</span>
					</button>`)
					.join("")
			);
		}

		$profile_strip.on("click", ".us-profile", function () {
			const p = state.profiles[this.dataset.i];
			// Clicking the active profile clears it; any other replaces the ticked roles with its roles
			const known = new Set((state.roles || []).map((r) => r.name));
			state.picked = profile_matches(p) ? new Set() : new Set(p.roles.filter((r) => known.has(r)));
			paint_roles();
			this.scrollIntoView({ block: "nearest", inline: "nearest" });
		});

		// ---------- manage roles of the signed-in user ----------

		function show_roles(user) {
			show_create(true);
			state.editing = user.name;
			state.original = new Set();
			$root.addClass("us-roles-mode");
			$create.find(".us-create-title").text(t("Manage roles"));
			$create.find(".us-create-sub").text(t("Tick the roles {0} should have. Unticked roles are removed on save.", [display_name(user)]));
			frappe.call({ method: `${API}.get_user_roles`, args: { user: user.name }, type: "GET" }).then((r) => {
				state.original = new Set(r.message || []);
				state.picked = new Set(state.original);
				load_roles();
			});
		}

		$create.find(".us-roles-cancel").on("click", () => show_create(false));

		$create.find(".us-roles-save").on("click", () => {
			const $buttons = $create.find(".us-btn").prop("disabled", true);
			frappe
				.call({
					method: `${API}.set_user_roles`,
					args: { user: state.editing, roles: [...state.picked] },
					type: "POST",
				})
				.then(() => {
					frappe.show_alert?.({ message: t("Roles updated"), indicator: "green" });
					// Desk caches the user's roles in boot info, so reload to apply them
					window.location.reload();
				})
				.catch(() => $buttons.prop("disabled", false));
		});

		$name.on("input", () => {
			if (!email_touched) {
				const s = slug($name.val());
				$email.val(s ? `${s}@example.com` : "");
			}
		});
		// Clearing the email hands control back to auto-fill
		$email.on("input", () => (email_touched = $email.val() !== ""));
		$role_search.on("input", paint_roles);
		// Enter in the role filter should not submit the form
		$role_search.on("keydown", (e) => {
			if (e.key === "Enter") {
				e.preventDefault();
				$role_list.find(".us-role input").first().trigger("click");
			}
		});

		function load_roles() {
			if (state.roles) return paint_roles();
			frappe.call({ method: `${API}.get_assignable_roles`, type: "GET" }).then((r) => {
				state.roles = r.message || [];
				paint_roles();
			});
		}

		function paint_roles() {
			if (!state.roles) return;
			const q = $role_search.val().trim();
			const rows = search(state.roles, q, (r) => r.name);
			const row_html = (r) => `<label class="us-role">
				<input type="checkbox" value="${esc(r.name)}" ${state.picked.has(r.name) ? "checked" : ""}>
				<span class="us-role-name">${mark_match(r.name, q)}</span>
				${r.desk_access ? "" : `<span class="us-chip us-chip--web">${t("Portal")}</span>`}
				<span class="us-role-tag"></span>
			</label>`;
			// Grouped by what the user had when the list was drawn, so rows don't jump while ticking
			const first = state.editing ? state.original : state.picked;
			const top = rows.filter((r) => first.has(r.name));
			const rest = rows.filter((r) => !first.has(r.name));
			const head = state.editing ? t("Current roles ({0})", [top.length]) : t("Selected ({0})", [top.length]);
			const group = (title, list) => (list.length ? `<div class="us-group">${title}</div>` + list.map(row_html).join("") : "");
			$role_list.html(
				rows.length
					? group(head, top) + (top.length ? group(t("Other roles"), rest) : rest.map(row_html).join(""))
					: `<div class="us-empty">${t("No roles match")}</div>`
			);
			$role_list.find("input").on("change", function () {
				this.checked ? state.picked.add(this.value) : state.picked.delete(this.value);
				paint_picked();
			});
			paint_picked();
		}

		function paint_picked() {
			const picked = [...state.picked];
			$create.find(".us-picked-count").text(t("{0} selected", [picked.length]));
			const $status = $create.find(".us-form-status");

			if (state.editing) {
				const added = picked.filter((r) => !state.original.has(r));
				const removed = [...state.original].filter((r) => !state.picked.has(r));
				$status.html(
					added.length || removed.length
						? `<span class="us-status-add">${t("{0} added", [added.length])}</span> · <span class="us-status-remove">${t("{0} removed", [removed.length])}</span>`
						: t("No changes yet")
				);
				$role_list.find(".us-role").each(function () {
					const name = $(this).find("input").val();
					const adding = state.picked.has(name) && !state.original.has(name);
					const removing = !state.picked.has(name) && state.original.has(name);
					$(this).toggleClass("is-adding", adding).toggleClass("is-removing", removing)
						.find(".us-role-tag").text(adding ? t("Adding") : removing ? t("Removing") : "");
				});
				$create.find(".us-roles-save").prop("disabled", !added.length && !removed.length);
				return;
			}
			$profile_strip.find(".us-profile").each(function () {
				const on = profile_matches(state.profiles[this.dataset.i]);
				$(this).toggleClass("is-on", on).attr("aria-pressed", on);
			});
			// Frappe derives the user type from the roles: any desk-access role makes a System User
			const desk = picked.some((r) => state.roles?.find((x) => x.name === r)?.desk_access);
			$status.html(t("User type: {0}", [`<b>${desk ? t("System User") : t("Website User")}</b>`]));
		}

		$create.on("submit", (e) => {
			e.preventDefault();
			if (!state.editing) create_user(true);
		});
		$create.find(".us-create-only").on("click", () => create_user(false));

		function create_user(and_switch) {
			const full_name = $name.val().trim();
			const email = $email.val().trim();
			if (!full_name) return $name.trigger("focus");
			if (!email) return $email.trigger("focus");

			const $buttons = $create.find(".us-btn").prop("disabled", true);
			if (and_switch) frappe.dom?.freeze?.(t("Creating {0}...", [esc(full_name)]));
			frappe
				.call({
					method: `${API}.create_test_user`,
					args: { full_name, email, roles: [...state.picked], switch: and_switch ? 1 : 0 },
					type: "POST",
				})
				.then((r) => {
					const u = { ...r.message, name: r.message.name };
					store.remember(u);
					if (and_switch) {
						window.location.pathname.startsWith("/app")
							? (window.location.href = "/app")
							: window.location.reload();
						return;
					}
					$buttons.prop("disabled", false);
					frappe.show_alert?.({ message: t("Created {0}", [esc(full_name)]), indicator: "green" });
					show_create(false);
					fetch_users();
				})
				.catch(() => {
					$buttons.prop("disabled", false);
					frappe.dom?.unfreeze?.();
				});
		}

		// ---------- doctype access (role permissions) ----------

		const COMMON_RIGHTS = ["select", "read", "write", "create", "delete", "submit", "cancel", "amend"];
		const RIGHT_LABELS = {
			select: t("Select"), read: t("Read"), write: t("Write"), create: t("Create"), delete: t("Delete"),
			submit: t("Submit"), cancel: t("Cancel"), amend: t("Amend"), print: t("Print"), email: t("Email"),
			report: t("Report"), import: t("Import"), export: t("Export"), share: t("Share"),
		};
		// Turning a right on also turns on what Frappe requires for it; turning one off drops what needs it
		const NEEDS = { submit: ["write"], cancel: ["submit"], amend: ["cancel"], import: ["create"] };
		const $access = $root.find(".us-access");
		const $dt_input = $access.find(".us-access-doctype");
		const $dt_list = $access.find(".us-combo-list");
		const $access_roles = $access.find(".us-access-roles");
		const $role_find = $access.find(".us-access-role-search");
		const $suggest = $access.find(".us-access-suggest");
		const $access_more = $access.find(".us-access-more input");
		let dt_timer;

		function show_access(on, doctype) {
			if (on && state.info) show_info(false);
			if (on && state.creating) show_create(false);
			state.access = on ? { data: null, extra: [], edits: {} } : null;
			$root.toggleClass("us-access-mode", on);
			if (!on) {
				$search.trigger("focus");
				return;
			}
			$dt_input.val(doctype || "");
			$role_find.val("");
			if (doctype) load_access(doctype);
			else paint_access();
			setTimeout(() => $dt_input.trigger("focus"), 30);
		}

		$access.find(".us-access-cancel").on("click", () => show_access(false));

		// ----- DocType picker: our own list, so it matches the widget (a <datalist> uses the browser's menu) -----

		let dt_options = [];
		let dt_active = -1;
		let dt_request = 0;

		function open_dt_list(open) {
			$dt_list.prop("hidden", !open || !$dt_list.children().length);
			$dt_input.attr("aria-expanded", String(!$dt_list.prop("hidden")));
		}

		function paint_dt_list(q) {
			const mark = (name) => mark_match(name, q);
			$dt_list.html(
				dt_options.length
					? dt_options
							.map((d, i) => `<span class="us-combo-option ${i === dt_active ? "is-active" : ""}" role="option" id="us-dt-${i}"
								aria-selected="${i === dt_active}" data-i="${i}">
								<span class="us-combo-name">${mark(d.name)}</span><span class="us-combo-meta">${esc(d.module || "")}</span>
							</span>`)
							.join("")
					: `<span class="us-combo-empty">${t("No DocType matches “{0}”", [esc(q)])}</span>`
			);
			$dt_input.attr("aria-activedescendant", dt_active >= 0 ? `us-dt-${dt_active}` : null);
			open_dt_list(true);
		}

		function pick_dt(name) {
			$dt_input.val(name);
			open_dt_list(false);
			load_access(name);
		}

		$dt_input.on("input focus", (e) => {
			clearTimeout(dt_timer);
			const q = $dt_input.val().trim();
			// Focusing a field that already shows the loaded doctype shouldn't pop the list open
			if (e.type === "focus" && q === state.access?.data?.doctype) return;
			dt_timer = setTimeout(() => {
				const request = ++dt_request;
				frappe.call({ method: `${API}.search_doctypes`, args: { txt: q }, type: "GET" }).then((r) => {
					if (request !== dt_request || !$dt_input.is(":focus")) return;
					dt_options = r.message || [];
					dt_active = dt_options.length ? 0 : -1;
					paint_dt_list(q);
				});
			}, e.type === "focus" ? 0 : 150);
		});

		$dt_input.on("keydown", (e) => {
			const open = !$dt_list.prop("hidden");
			if ((e.key === "ArrowDown" || e.key === "ArrowUp") && dt_options.length) {
				e.preventDefault();
				dt_active = (dt_active + (e.key === "ArrowDown" ? 1 : -1) + dt_options.length) % dt_options.length;
				paint_dt_list($dt_input.val().trim());
				$dt_list.find(".is-active")[0]?.scrollIntoView({ block: "nearest" });
			} else if (e.key === "Enter") {
				e.preventDefault();
				const typed = $dt_input.val().trim();
				const exact = dt_options.find((d) => d.name.toLowerCase() === typed.toLowerCase());
				if (open && dt_options[dt_active]) pick_dt(dt_options[dt_active].name);
				else if (exact || typed) pick_dt(exact ? exact.name : typed);
			} else if (e.key === "Escape" && open) {
				// Close only the list, not the whole screen
				e.preventDefault();
				e.stopPropagation();
				open_dt_list(false);
			}
		});

		// mousedown, not click: picking must happen before the input's blur closes the list
		$dt_list.on("mousedown", ".us-combo-option", function (e) {
			e.preventDefault();
			pick_dt(dt_options[this.dataset.i].name);
		});
		$dt_input.on("blur", () => {
			setTimeout(() => open_dt_list(false), 100);
			// Leaving the field with a half-typed name puts the loaded doctype back
			if (state.access?.data && !$dt_input.val().trim()) $dt_input.val(state.access.data.doctype);
		});

		function load_access(doctype) {
			if (!state.access || state.access.data?.doctype === doctype) return;
			if (has_access_edits()) {
				frappe.show_alert?.({ message: t("Save or cancel your changes first"), indicator: "orange" });
				$dt_input.val(state.access.data.doctype);
				return;
			}
			$access_roles.html(empty_state(t("Loading...")));
			frappe
				.call({ method: `${API}.get_doctype_access`, args: { doctype }, type: "GET" })
				.then((r) => {
					if (!state.access) return;
					state.access = { data: r.message, extra: [], edits: {} };
					$role_find.val("");
					$access.find(".us-access-advanced").attr("href", `/app/permission-manager/${encodeURIComponent(doctype)}`);
					paint_access();
				})
				.catch(() => {
					if (!state.access) return;
					state.access.data = null;
					paint_access();
				});
		}

		const has_access_edits = () => Object.values(state.access?.edits || {}).some((e) => Object.keys(e).length);

		function access_value(row, right) {
			const edit = state.access.edits[row.role]?.[right];
			return edit ?? (row.perms[right] || 0);
		}

		function access_rows() {
			const data = state.access.data;
			const known = new Set(data.roles.map((r) => r.role));
			// The viewed user's roles always get a row, even with no rule yet, so the fix is one click away
			const mine = data.user_roles.filter((r) => !known.has(r)).map((role) => ({ role, perms: {}, user_has: true }));
			const extra = state.access.extra.filter((r) => !known.has(r) && !data.user_roles.includes(r)).map((role) => ({ role, perms: {} }));
			const rows = [...data.roles, ...mine, ...extra];
			return rows.sort((a, b) => !!b.user_has - !!a.user_has || !!a.locked - !!b.locked);
		}

		function set_right(row, right, on) {
			const rights = state.access.data.rights;
			const values = {};
			const apply = (r, v) => rights.includes(r) && (values[r] = v);
			apply(right, on ? 1 : 0);
			if (on) {
				// Anything but Select needs Read to be useful
				if (right !== "select") apply("read", 1);
				for (let r = right; NEEDS[r]; ) NEEDS[r].forEach((n) => apply((r = n), 1));
				if (["submit", "cancel", "amend"].includes(right)) apply("write", 1);
			} else {
				const drop = (r) => Object.entries(NEEDS).forEach(([k, v]) => v.includes(r) && (apply(k, 0), drop(k)));
				drop(right);
				if (right === "write") ["submit", "cancel", "amend"].forEach((r) => apply(r, 0));
				if (right === "read") rights.filter((r) => r !== "select").forEach((r) => apply(r, 0));
			}
			const edits = (state.access.edits[row.role] ||= {});
			Object.entries(values).forEach(([r, v]) => (v === (row.perms[r] || 0) ? delete edits[r] : (edits[r] = v)));
			paint_access();
		}

		function paint_access() {
			const data = state.access?.data;
			const $summary = $access.find(".us-access-summary").empty();
			$access.find(".us-access-tools, .us-access-actions").toggle(!!data);
			if (!data) {
				$access_roles.html(empty_state(t("Type a doctype name above, for example Sales Invoice.")));
				return;
			}
			const show_all = $access_more.prop("checked");
			const shown_rights = data.rights.filter((r) => show_all || COMMON_RIGHTS.includes(r));
			const all_rows = access_rows();
			const q = $role_find.val().trim();
			const rows = search(all_rows, q, (r) => r.role);
			const me = state.ctx?.current_user || boot_user_info(data.user);

			// What the viewed user ends up with, from every role they have (including automatic ones)
			const mine = all_rows.filter((r) => r.user_has);
			const can = shown_rights.filter((right) => mine.some((row) => access_value(row, right)));
			const cannot = shown_rights.filter((right) => !can.includes(right));
			const pills = (rights, cls) => rights.map((r) => `<span class="us-access-pill ${cls}">${RIGHT_LABELS[r]}</span>`).join("");
			$summary.html(`
				<div class="us-access-summary-title">${t("What {0} can do", [`<b>${esc(display_name(me))}</b>`])}</div>
				<div class="us-access-summary-row">
					<span class="us-access-summary-label">${t("Allowed")}</span>
					<span class="us-access-pills">${can.length ? pills(can, "is-yes") : `<span class="us-access-none">${t("Nothing yet")}</span>`}</span>
				</div>
				${cannot.length ? `<div class="us-access-summary-row">
					<span class="us-access-summary-label">${t("Missing")}</span>
					<span class="us-access-pills">${pills(cannot, "is-no")}</span>
				</div>` : ""}
				${data.only_if_creator.length ? `<small>${t("Rules limited to the creator's own documents are not shown: {0}", [esc(data.only_if_creator.join(", "))])}</small>` : ""}
			`);

			const role_html = (row) => {
				const buttons = shown_rights
					.map((right) => {
						const on = access_value(row, right);
						const changed = state.access.edits[row.role]?.[right] !== undefined;
						return `<button type="button" class="us-right ${on ? "is-on" : ""} ${changed ? "is-changed" : ""}"
							data-right="${right}" aria-pressed="${!!on}" ${row.locked ? "disabled" : ""}>${RIGHT_LABELS[right]}</button>`;
					})
					.join("");
				return `<div class="us-access-role ${row.user_has ? "is-mine" : ""}" data-role="${esc(row.role)}">
					<b class="us-access-role-name" title="${esc(row.role)}">${esc(row.role)}</b>
					<div class="us-access-rights">${buttons}</div>
				</div>`;
			};
			// Grouped so the viewed user's roles (the ones that fix their access) are clearly first
			const groups = [
				[t("{0}'s roles", [esc(display_name(me))]), rows.filter((r) => r.user_has && !r.locked)],
				[t("Other roles with access"), rows.filter((r) => !r.user_has && !r.locked)],
				[t("Everyone (change in Role Permission Manager)"), rows.filter((r) => r.locked)],
			];
			$access_roles.html(
				groups
					.filter(([, list]) => list.length)
					.map(([title, list]) => `<div class="us-group">${title}</div>` + list.map(role_html).join(""))
					.join("") || (q ? "" : empty_state(t("No role has access yet. Search above to add one.")))
			);
			$access_roles.find(".us-right").on("click", function () {
				const role = $(this).closest(".us-access-role").data("role");
				const row = rows.find((r) => r.role === String(role));
				set_right(row, this.dataset.right, this.getAttribute("aria-pressed") !== "true");
			});

			// Roles without a rule yet that match the search: one click adds them as a row
			const listed = new Set(all_rows.map((r) => r.role));
			const addable = q ? search(data.assignable_roles.filter((r) => !listed.has(r)), q).slice(0, 8) : [];
			$suggest.html(
				addable.length
					? `<span class="us-group">${t("Add a role")}</span>` +
							addable.map((r) => `<button type="button" class="us-access-suggest-item" data-role="${esc(r)}">${ICONS.plus}${esc(r)}</button>`).join("")
					: q && !rows.length
						? empty_state(t("No roles match “{0}”", [esc(q)]))
						: ""
			);

			const count = Object.values(state.access.edits).reduce((n, e) => n + Object.keys(e).length, 0);
			$access.find(".us-access-changes").text(count ? t("{0} unsaved", [count]) : "");
			$access.find(".us-access-save").prop("disabled", !count).text(count ? t("Save & reload") : t("Save"));
		}

		function add_access_role(role) {
			if (!role) return;
			state.access.extra.push(role);
			$role_find.val("");
			paint_access();
			const $row = $access_roles.find(`.us-access-role[data-role="${CSS.escape(role)}"]`);
			$row.addClass("is-new")[0]?.scrollIntoView({ block: "nearest" });
			$row.find(".us-right").first().trigger("focus");
		}

		$suggest.on("click", ".us-access-suggest-item", function () {
			add_access_role(String($(this).data("role")));
		});
		$role_find.on("input", paint_access);
		$role_find.on("keydown", (e) => {
			if (e.key !== "Enter") return;
			e.preventDefault();
			// Enter adds the first suggestion, or jumps to the only matching row
			const first = $suggest.find(".us-access-suggest-item").first().data("role");
			if (first) add_access_role(String(first));
			else $access_roles.find(".us-right").first().trigger("focus");
		});
		$access_more.on("change", paint_access);

		// Role Permission Manager is for System Managers only. While switched into someone without that
		// role the page would say Not permitted, so go back to your own account first and open it there.
		$access.find(".us-access-advanced").on("click", function (e) {
			const roles = frappe.user_roles || frappe.boot?.user?.roles || [];
			if (!who.is_switched || current_user() === "Administrator" || roles.includes("System Manager")) return;
			e.preventDefault();
			if (has_access_edits()) {
				frappe.show_alert?.({ message: t("Save or cancel your changes first"), indicator: "orange" });
				return;
			}
			switch_to({ name: who.real, full_name: who.real_full_name || who.real }, { back: true, to: this.href });
		});

		$access.find(".us-access-save").on("click", () => {
			const $buttons = $access.find(".us-btn").prop("disabled", true);
			frappe
				.call({
					method: `${API}.set_doctype_access`,
					args: { doctype: state.access.data.doctype, changes: state.access.edits },
					type: "POST",
				})
				.then(() => {
					frappe.show_alert?.({ message: t("Access to {0} updated", [esc(state.access.data.doctype)]), indicator: "green" });
					// Desk caches permissions in boot info, so reload to apply them
					window.location.reload();
				})
				.catch(() => $buttons.prop("disabled", false));
		});

		return {
			open,
			open_access(doctype) {
				open();
				show_access(true, doctype);
			},
		};
	}

	// ---------- doctype from the current desk route ----------

	const DOCTYPE_VIEWS = ["List", "Form", "Report", "Tree", "Image", "Kanban", "Calendar", "Gantt", "Dashboard", "Map"];

	function route_doctype() {
		const route = frappe.get_route?.() || [];
		return DOCTYPE_VIEWS.includes(route[0]) && route[1] ? route[1] : "";
	}

	// ---------- "Not permitted" while switched: offer to fix it ----------

	function watch_permission_errors() {
		let last_shown = 0;
		const offer_fix = (doctype) => {
			doctype = doctype || route_doctype();
			if (!doctype || Date.now() - last_shown < 3000) return;
			last_shown = Date.now();
			const me = boot_user_info(current_user());
			frappe.show_alert?.(
				{
					message: `${t("{0} has no access to {1}.", [esc(display_name(me)), `<b>${esc(doctype)}</b>`])}
						<a href="#" class="us-fix-access" data-doctype="${esc(doctype)}">${t("Fix access")}</a>`,
					indicator: "orange",
				},
				10
			);
		};

		$(document).on("click", ".us-fix-access", function (e) {
			e.preventDefault();
			frappe.user_switcher.open_access?.(this.dataset.doctype);
		});

		$(document).ajaxComplete((e, xhr, settings) => {
			if (xhr.responseJSON?.exc_type !== "PermissionError" || String(settings.url).includes("user_switcher.api")) return;
			let data = settings.data;
			try {
				data = typeof data === "string" ? Object.fromEntries(new URLSearchParams(data)) : data;
			} catch (err) {}
			offer_fix(data?.doctype);
		});

		// Desk shows its own Not Permitted page without a server error when the doctype isn't readable
		const show_not_permitted = frappe.show_not_permitted;
		if (show_not_permitted) {
			frappe.show_not_permitted = function () {
				const out = show_not_permitted.apply(this, arguments);
				offer_fix();
				return out;
			};
		}
	}

	// ---------- Ctrl+Shift+A: back to the real account ----------

	// Registered at module level (not inside the widget) so it works on every page, with the
	// widget closed, hidden, or not rendered yet. The server still decides if it's allowed.
	document.addEventListener(
		"keydown",
		(e) => {
			if (!is_back_shortcut(e) || current_user() === "Guest") return;
			e.preventDefault();
			e.stopPropagation();
			// Desk knows from boot; website pages may not have loaded that yet, so ask the server
			if (!who.is_switched && frappe.boot?.user) {
				frappe.show_alert?.({
					message: t("Already signed in as {0}", [esc(display_name(boot_user_info(current_user())))]),
					indicator: "blue",
				});
				return;
			}
			switch_back();
		},
		true
	);

	// ---------- boot ----------

	window.frappe.user_switcher = { switch_to, switch_back };

	on_ready(() => {
		if (current_user() === "Guest") return;
		// Desk knows from boot whether we're switched; show the banner before anything loads
		if (who.is_switched && frappe.boot?.user) {
			render_banner(boot_user_info(current_user()), boot_user_info(who.real));
		}
		check_allowed().then((allowed) => {
			if (!allowed) return;
			const widget = render_widget();
			frappe.user_switcher.open = widget.open;
			frappe.user_switcher.open_access = widget.open_access;
			if (who.is_switched) watch_permission_errors();
		});
	});
})();
