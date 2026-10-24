const { defineConfig } = require("cypress");

module.exports = defineConfig({
	projectId: "user_switcher",
	viewportWidth: 1440,
	viewportHeight: 900,
	defaultCommandTimeout: 15000,
	pageLoadTimeout: 30000,
	requestTimeout: 15000,
	responseTimeout: 15000,
	video: false,
	screenshotOnRunFailure: true,
	retries: {
		runMode: 1,
		openMode: 0,
	},
	env: {
		adminPassword: process.env.CYPRESS_adminPassword || "admin",
		testUser: process.env.CYPRESS_testUser || "Administrator",
	},
	e2e: {
		baseUrl: process.env.CYPRESS_baseUrl || "http://account.localhost:8001",
		testIsolation: false,
		specPattern: ["cypress/e2e/**/*.cy.{js,jsx,ts,tsx}"],
		supportFile: "cypress/support/e2e.js",
		setupNodeEvents(on, config) {
			return config;
		},
	},
});
