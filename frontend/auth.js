
const API_HOST = window.location.hostname || "127.0.0.1";
const API_URL = `http://${API_HOST}:5000`;

document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("auth-form");

    if (!form) {
        console.error("Could not find #auth-form. Check login.html.");
        return;
    }

    const loginTab = document.getElementById("login-tab");
    const signupTab = document.getElementById("signup-tab");
    const username = document.getElementById("username");
    const email = document.getElementById("email");
    const identifier = document.getElementById("login-identifier");
    const password = document.getElementById("password");
    const confirmPassword = document.getElementById("confirm-password");
    const message = document.getElementById("form-message");
    const submitButton = document.getElementById("submit-button");
    const submitLabel = document.getElementById("submit-label");

    let mode = "login";
    let submitting = false;

    function showMessage(text, success = false) {
        message.textContent = text;
        message.className = success
            ? "form-message success"
            : "form-message error";
        message.hidden = false;
    }

    function switchMode(nextMode) {
        mode = nextMode;
        const signup = mode === "signup";

        document.getElementById("username-group").hidden = !signup;
        document.getElementById("email-group").hidden = !signup;
        document.getElementById("identifier-group").hidden = signup;
        document.getElementById("confirm-group").hidden = !signup;

        username.disabled = !signup;
        email.disabled = !signup;
        identifier.disabled = signup;

        username.required = signup;
        email.required = signup;
        identifier.required = !signup;
        confirmPassword.disabled = !signup;
        confirmPassword.required = signup;

        loginTab.classList.toggle("active", !signup);
        signupTab.classList.toggle("active", signup);

        document.getElementById("form-title").textContent =
            signup ? "Create Account" : "Welcome Back";

        document.getElementById("form-kicker").textContent =
            signup ? "JOIN THE JOURNEY" : "YOUR JOURNEY CONTINUES";

        document.getElementById("form-description").textContent =
            signup
                ? "Create your account to plan your next journey."
                : "Log in to continue your railway journey.";

        submitLabel.textContent = signup ? "Create Account" : "Log In";
        password.autocomplete = signup ? "new-password" : "current-password";
        message.hidden = true;
    }

    loginTab.addEventListener("click", () => switchMode("login"));
    signupTab.addEventListener("click", () => switchMode("signup"));

    document.getElementById("toggle-password")?.addEventListener("click", () => {
        password.type =
            password.type === "password" ? "text" : "password";
    });

    document.getElementById("toggle-confirm-password")?.addEventListener("click", () => {
        confirmPassword.type =
            confirmPassword.type === "password" ? "text" : "password";
    });

    form.addEventListener("submit", async (event) => {
        event.preventDefault();

        if (submitting) return;

        const pass = password.value;
        let endpoint;
        let payload;

        if (mode === "signup") {
            payload = {
                name: username.value.trim(),
                email: email.value.trim().toLowerCase(),
                password: pass
            };

            if (!payload.name || !payload.email || !pass ||
                !confirmPassword.value) {
                showMessage("Please fill in all required fields.");
                return;
            }

            if (pass.length < 6) {
                showMessage("Password must contain at least 6 characters.");
                return;
            }

            if (pass !== confirmPassword.value) {
                showMessage("Passwords do not match.");
                return;
            }

            endpoint = `${API_URL}/api/signup`;
        } else {
            payload = {
                email: identifier.value.trim().toLowerCase(),
                password: pass
            };

            if (!payload.email || !pass) {
                showMessage("Enter your email and password.");
                return;
            }

            endpoint = `${API_URL}/api/login`;
        }

        submitting = true;
        submitButton.disabled = true;
        submitLabel.textContent =
            mode === "signup" ? "Creating Account..." : "Logging In...";

        try {
            const response = await fetch(endpoint, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(
                    data.error || data.message || `Request failed (${response.status})`
                );
            }

            if (mode === "signup") {
                showMessage(
                    data.message || "Account created. Please log in.",
                    true
                );

                switchMode("login");
                identifier.value = payload.email;
                password.value = "";
                return;
            }

            if (!data.user) {
                throw new Error("The backend did not return user details.");
            }

            sessionStorage.setItem(
                "railwayUser",
                JSON.stringify(data.user)
            );

            if (data.token) {
                sessionStorage.setItem("railwayToken", data.token);
            }

            window.location.href = "./index.html";

        } catch (error) {
            console.error("Login error:", error);

            showMessage(
                error instanceof TypeError
                    ? "Cannot connect to Flask. Check that it is running on port 5000."
                    : error.message || "Login failed."
            );
        } finally {
            submitting = false;
            submitButton.disabled = false;
            submitLabel.textContent =
                mode === "signup" ? "Create Account" : "Log In";
        }
    });

    switchMode("login");
    console.log("AUTH.JS LOADED — current login handler attached.");
});
