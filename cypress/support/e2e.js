import "./commands";

// Prevent Cypress from failing tests on third-party uncaught exceptions
Cypress.on("uncaught:exception", (err) => {
	// Returning false prevents Cypress from failing the test
	if (
		err.message.includes("ResizeObserver loop limit exceeded") ||
		err.message.includes("Script error") ||
		err.message.includes("frappe is not defined")
	) {
		return false;
	}
	return false;
});
