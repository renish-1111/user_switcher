describe("User Switcher E2E Tests", () => {
	before(() => {
		cy.login();
		cy.visit("/app");
		cy.get(".layout-main-section, .page-container, body", { timeout: 15000 }).should("be.visible");
	});

	beforeEach(() => {
		cy.visit("/app");
		cy.get("#us-floating-container", { timeout: 15000 }).should("exist");
	});

	context("Widget Trigger & UI Display", () => {
		it("renders the floating switcher container and trigger button", () => {
			cy.get("#us-floating-container").should("exist").and("be.visible");
			cy.get("#us-floating-container .us-trigger").should("be.visible");
			cy.get("#us-floating-container .us-trigger-avatar").should("exist");
			cy.get("#us-floating-container .us-trigger-badge").should("exist");
		});

		it("opens the switcher card dialog when trigger is clicked", () => {
			cy.get("#us-floating-container .us-trigger").click();
			cy.get("#us-floating-container").should("have.class", "us-open");
			cy.get("#us-floating-container .us-card")
				.should("be.visible")
				.and("have.attr", "aria-hidden", "false");
		});

		it("closes the switcher card dialog when Escape key is pressed", () => {
			cy.openUserSwitcher();
			cy.get("body").type("{esc}");
			cy.get("#us-floating-container").should("not.have.class", "us-open");
			cy.get("#us-floating-container .us-card").should("have.attr", "aria-hidden", "true");
		});

		it("toggles the switcher dialog with Ctrl+Shift+S keyboard shortcut", () => {
			cy.get("body").trigger("keydown", {
				ctrlKey: true,
				shiftKey: true,
				key: "S",
				code: "KeyS",
				which: 83,
			});
			cy.get("#us-floating-container").should("have.class", "us-open");
			cy.get("#us-floating-container .us-card").should("be.visible");

			cy.get("body").trigger("keydown", {
				ctrlKey: true,
				shiftKey: true,
				key: "S",
				code: "KeyS",
				which: 83,
			});
			cy.get("#us-floating-container").should("not.have.class", "us-open");
		});
	});

	context("User Search & Filter Tabs", () => {
		beforeEach(() => {
			cy.openUserSwitcher();
		});

		afterEach(() => {
			cy.closeUserSwitcher();
		});

		it("displays the search bar and filter tabs", () => {
			cy.get(".us-search input")
				.should("be.visible")
				.and("have.attr", "placeholder");
			cy.get(".us-filters .us-filter").should("have.length.at.least", 3);
			cy.get('.us-filters .us-filter[data-type=""]').should("have.class", "active");
		});

		it("filters users dynamically when typing in search input", () => {
			cy.get(".us-search input").type("renish");
			cy.wait(300);

			cy.get(".us-list .us-item").should("have.length.at.least", 1);
			cy.get(".us-list").should("contain.text", "renish");
		});

		it("switches filter tabs between All, System, and Website users", () => {
			// Click System tab
			cy.get('.us-filters .us-filter[data-type="System User"]').click();
			cy.get('.us-filters .us-filter[data-type="System User"]').should("have.class", "active");
			cy.get('.us-filters .us-filter[data-type=""]').should("not.have.class", "active");

			// Click Website tab
			cy.get('.us-filters .us-filter[data-type="Website User"]').click();
			cy.get('.us-filters .us-filter[data-type="Website User"]').should("have.class", "active");

			// Reset to All
			cy.get('.us-filters .us-filter[data-type=""]').click();
			cy.get('.us-filters .us-filter[data-type=""]').should("have.class", "active");
		});

		it("displays an empty state message when search yields no matches", () => {
			cy.get(".us-search input").type("NonExistentUser123456XYZ");
			cy.wait(300);
			cy.get(".us-list .us-empty").should("be.visible");
		});
	});

	context("Pinning and Unpinning Users", () => {
		beforeEach(() => {
			cy.openUserSwitcher();
		});

		afterEach(() => {
			cy.closeUserSwitcher();
		});

		it("pins and unpins a user", () => {
			// Pin user
			cy.get(".us-list .us-item")
				.first()
				.find(".us-pin")
				.click();

			cy.get(".us-list .us-pin.is-pinned").should("exist");

			// Unpin user
			cy.get(".us-list .us-pin.is-pinned")
				.first()
				.click();

			cy.get(".us-list .us-pin.is-pinned").should("not.exist");
		});
	});

	context("Quick Action Panels (Roles, Access & New Test User)", () => {
		beforeEach(() => {
			cy.openUserSwitcher();
		});

		afterEach(() => {
			cy.closeUserSwitcher();
		});

		it("hides the Manage Roles tile for Administrator", () => {
			cy.get(".us-tile-roles").should("be.hidden");
		});

		it("opens and navigates back from the Doctype Access panel", () => {
			cy.get(".us-tile-access").should("be.visible").click();

			cy.get("#us-floating-container").should("have.class", "us-access-mode");
			cy.get(".us-access").should("be.visible");
			cy.get(".us-access-doctype").should("be.visible");

			// Return to main browse view via back button in header
			cy.get(".us-identity .us-head-back").click();
			cy.get("#us-floating-container").should("not.have.class", "us-access-mode");
			cy.get(".us-browse").should("be.visible");
		});

		it("opens Doctype Access, types a doctype, and cancels changes", () => {
			cy.get(".us-tile-access").should("be.visible").click();

			cy.get(".us-access-doctype").type("ToDo{enter}");
			cy.wait(500);

			// Bottom bar actions become visible with data
			cy.get(".us-access-actions").should("be.visible");
			cy.get(".us-access-cancel").should("be.visible").click();

			// Returns to browse
			cy.get("#us-floating-container").should("not.have.class", "us-access-mode");
			cy.get(".us-browse").should("be.visible");
		});

		it("opens and verifies the New Test User form", () => {
			cy.get(".us-new").should("be.visible").click();

			cy.get("#us-floating-container").should("have.class", "us-creating");
			cy.get(".us-create").should("be.visible");
			cy.get(".us-new-name").should("be.visible");
			cy.get(".us-new-email").should("be.visible");
			cy.get(".us-create-only").should("be.visible");
			cy.get('button[type="submit"]').contains(/Create & switch/i).should("be.visible");

			// Return to browse via header back button
			cy.get(".us-identity .us-head-back").click();
			cy.get("#us-floating-container").should("not.have.class", "us-creating");
			cy.get(".us-browse").should("be.visible");
		});
	});

	context("How-to Guide Modal", () => {
		beforeEach(() => {
			cy.openUserSwitcher();
		});

		afterEach(() => {
			cy.closeUserSwitcher();
		});

		it("opens and closes the How-to Guide from the info button", () => {
			cy.get(".us-info-btn").should("be.visible").click();
			cy.get(".us-info").should("be.visible");
			cy.get(".us-info").should("contain.text", "How to use User Switcher");

			// Clicking info button again toggles back to browse
			cy.get(".us-info-btn").click();
			cy.get(".us-info").should("not.be.visible");
			cy.get(".us-browse").should("be.visible");
		});
	});

	context("Hide and Restore Widget", () => {
		it("hides the widget container until reopened via shortcut", () => {
			cy.openUserSwitcher();
			cy.get(".us-hide").should("be.visible").click();

			cy.get("#us-floating-container").should("have.class", "us-hidden");

			// Re-open with Ctrl+Shift+S
			cy.get("body").trigger("keydown", {
				ctrlKey: true,
				shiftKey: true,
				key: "S",
				code: "KeyS",
				which: 83,
			});

			cy.get("#us-floating-container").should("not.have.class", "us-hidden");
			cy.closeUserSwitcher();
		});
	});

	context("User Switching and Session Restoration", () => {
		it("switches user and displays viewing-as banner, then switches back", () => {
			cy.intercept("POST", "**/user_switcher.api.switch_to_user*").as("switchCall");
			cy.intercept("POST", "**/user_switcher.api.switch_back*").as("switchBackCall");

			cy.openUserSwitcher();

			// Click the first user's text to switch
			cy.get(".us-list .us-item").first().find(".us-item-text").click();

			cy.wait("@switchCall").its("response.statusCode").should("eq", 200);

			// Page reloads into switched user session with visible viewing-as banner pill
			cy.get("#us-banner", { timeout: 25000 }).should("exist");
			cy.get("#us-banner .us-banner-pill", { timeout: 25000 })
				.should("be.visible")
				.and("contain.text", "Viewing as");

			// Click switch back button on banner
			cy.get("#us-banner .us-banner-back").should("be.visible").click();

			cy.wait("@switchBackCall").its("response.statusCode").should("eq", 200);

			// Banner disappears
			cy.get("#us-banner", { timeout: 25000 }).should("not.exist");
		});
	});
});
