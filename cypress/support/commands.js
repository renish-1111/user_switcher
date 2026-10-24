// ***********************************************
// Cypress custom commands for User Switcher & Frappe
// ***********************************************

Cypress.Commands.add("login", (email, password) => {
	email = email || Cypress.env("testUser") || "Administrator";
	password = password || Cypress.env("adminPassword") || "admin";

	return cy.request({
		url: "/api/method/login",
		method: "POST",
		body: {
			usr: email,
			pwd: password,
		},
		headers: {
			Accept: "application/json",
			"Content-Type": "application/json",
		},
	}).then((res) => {
		expect(res.status).to.eq(200);
	});
});

Cypress.Commands.add("call", (method, args = {}) => {
	return cy.window().then((win) => {
		const csrfToken = win.frappe?.csrf_token || "";
		return cy
			.request({
				url: `/api/method/${method}`,
				method: "POST",
				body: args,
				headers: {
					Accept: "application/json",
					"Content-Type": "application/json",
					"X-Frappe-CSRF-Token": csrfToken,
				},
			})
			.then((res) => {
				expect(res.status).to.eq(200);
				return res.body;
			});
	});
});

Cypress.Commands.add("openUserSwitcher", () => {
	cy.get("body").then(($body) => {
		if (!$body.find("#us-floating-container").hasClass("us-open")) {
			cy.get("#us-floating-container .us-trigger").click();
		}
	});
	cy.get("#us-floating-container").should("have.class", "us-open");
	cy.get("#us-floating-container .us-card").should("be.visible");
});

Cypress.Commands.add("closeUserSwitcher", () => {
	cy.get("body").then(($body) => {
		if ($body.find("#us-floating-container").hasClass("us-open")) {
			cy.get("body").type("{esc}");
		}
	});
	cy.get("#us-floating-container").should("not.have.class", "us-open");
});

Cypress.Commands.add("searchUser", (query) => {
	cy.openUserSwitcher();
	cy.get("#us-floating-container .us-search input")
		.clear()
		.type(query);
	cy.wait(150);
});

Cypress.Commands.add("filterUserType", (type) => {
	cy.openUserSwitcher();
	if (type === "All") {
		cy.get("#us-floating-container .us-filter").filter('[data-type=""]').click();
	} else {
		cy.get(`#us-floating-container .us-filter[data-type="${type}"]`).click();
	}
});
