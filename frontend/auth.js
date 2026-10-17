
const API_URL = "http://127.0.0.1:5000";

document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("auth-form");

    const loginTab = document.getElementById("login-tab");
    const signupTab = document.getElementById("signup-tab");

    const formTitle = document.getElementById("form-title");
    const formKicker = document.getElementById("form-kicker");
    const formDescription = document.getElementById("form-description");
    const submitLabel = document.getElementById("submit-label");
    const submitButton = document.getElementById("submit-button");
    const formMessage = document.getElementById("form-message");

    const usernameGroup = document.getElementById("username-group");
    const emailGroup = document.getElementById("email-group");
    const identifierGroup = document.getElementById("identifier-group");
    const confirmGroup = document.getElementById("confirm-group");

    const usernameInput = document.getElementById("username");
    const emailInput = document.getElementById("email");
    const identifierInput = document.getElementById("login-identifier");
    const passwordInput = document.getElementById("password");
    const confirmPasswordInput = document.getElementById("confirm-password");

    const togglePassword = document.getElementById("toggle-password");
    const toggleConfirmPassword = document.getElementById("toggle-confirm-password");

    let currentMode = "login";
    let isSubmitting = false;

    function showMessage(message, type = "error") {
        if (!formMessage) return;

        formMessage.textContent = message;
        formMessage.className = `form-message ${type}`;
        formMessage.hidden = false;
    }

    function clearMessage() {
        if (!formMessage) return;

        formMessage.textContent = "";
        formMessage.hidden = true;
        formMessage.className = "form-message";
    }

    function switchMode(mode) {
        if (isSubmitting) return;

        currentMode = mode;
        clearMessage();

        const isSignup = mode === "signup";

        if (loginTab) {
            loginTab.classList.toggle("active", !isSignup);
            loginTab.setAttribute("aria-selected", String(!isSignup));
        }

        if (signupTab) {
            signupTab.classList.toggle("active", isSignup);
            signupTab.setAttribute("aria-selected", String(isSignup));
        }

        if (formTitle) {
            formTitle.textContent = isSignup ? "Create Account" : "Welcome Back";
        }

        if (formKicker) {
            formKicker.textContent = isSignup
                ? "JOIN THE JOURNEY"
                : "YOUR JOURNEY CONTINUES";
        }

        if (formDescription) {
            formDescription.textContent = isSignup
                ? "Create your account to plan your next journey."
                : "Log in to continue your railway journey.";
        }

        if (submitLabel) {
            submitLabel.textContent = isSignup ? "Create Account" : "Log In";
        }

        // Show the correct fields for each mode.
        if (usernameGroup) usernameGroup.hidden = !isSignup;
        if (emailGroup) emailGroup.hidden = !isSignup;
        if (identifierGroup) identifierGroup.hidden = isSignup;
        if (confirmGroup) confirmGroup.hidden = !isSignup;

        // Set required fields correctly.
        if (usernameInput) usernameInput.required = isSignup;
        if (emailInput) emailInput.required = isSignup;
        if (identifierInput) identifierInput.required = !isSignup;
        if (passwordInput) {
            passwordInput.required = true;
            passwordInput.autocomplete = isSignup
                ? "new-password"
                : "current-password";
        }
        if (confirmPasswordInput) {
            confirmPasswordInput.required = isSignup;
        }

        // Hidden fields must not block form submission.
        if (usernameInput) usernameInput.disabled = !isSignup;
        if (emailInput) emailInput.disabled = !isSignup;
        if (identifierInput) identifierInput.disabled = isSignup;
        if (confirmPasswordInput) {
            confirmPasswordInput.disabled = !isSignup;
        }

        // Clear old values when switching modes.
        if (usernameInput) usernameInput.value = "";
        if (emailInput) emailInput.value = "";
        if (identifierInput) identifierInput.value = "";
        if (passwordInput) passwordInput.value = "";
        if (confirmPasswordInput) confirmPasswordInput.value = "";
    }

    async function parseResponse(response) {
        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            throw new Error(
                data.error || data.message || `Request failed (${response.status})`
            );
        }

        return data;
    }

    async function handleSubmit(event) {
        event.preventDefault();

        if (isSubmitting) return;

        clearMessage();

        const password = passwordInput?.value ?? "";

        let payload;
        let endpoint;

        if (currentMode === "signup") {
            const name = usernameInput?.value.trim() ?? "";
            const email = emailInput?.value.trim().toLowerCase() ?? "";
            const confirmPassword = confirmPasswordInput?.value ?? "";

            if (!name || !email || !password || !confirmPassword) {
                showMessage("Please fill in all required fields.");
                return;
            }

            if (password.length < 6) {
                showMessage("Password must contain at least 6 characters.");
                return;
            }

            if (password !== confirmPassword) {
                showMessage("Passwords do not match.");
                return;
            }

            payload = { name, email, password };
            endpoint = `${API_URL}/api/signup`;
        } else {
            const email = identifierInput?.value.trim().toLowerCase() ?? "";

            if (!email || !password) {
                showMessage("Please enter your email and password.");
                return;
            }

            payload = { email, password };
            endpoint = `${API_URL}/api/login`;
        }

        isSubmitting = true;

        if (submitButton) {
            submitButton.disabled = true;
            submitButton.setAttribute("aria-busy", "true");
        }

        if (submitLabel) {
            submitLabel.textContent =
                currentMode === "signup" ? "Creating Account..." : "Logging In...";
        }

        try {
            const response = await fetch(endpoint, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(payload)
            });

            const data = await parseResponse(response);

            if (currentMode === "signup") {
                const registeredEmail = payload.email;

                showMessage(
                    data.message || "Account created! You can now log in.",
                    "success"
                );

                form.reset();
                switchMode("login");

                // Keep the newly registered email ready for login.
                if (identifierInput) {
                    identifierInput.value = registeredEmail;
                }

                if (passwordInput) passwordInput.focus();
            } else {
                if (!data.user) {
                    throw new Error(
                        "Login response did not contain user details."
                    );
                }

                sessionStorage.setItem(
                    "railwayUser",
                    JSON.stringify(data.user)
                );

                showMessage(data.message || "Login successful!", "success");

                window.location.href = "index.html";
            }
        } catch (error) {
            if (error instanceof TypeError) {
                showMessage(
                    "Cannot connect to the server. Make sure Flask is running on port 5000."
                );
            } else {
                showMessage(
                    error.message || "Something went wrong. Please try again."
                );
            }

            console.error("Authentication error:", error);
        } finally {
            isSubmitting = false;

            if (submitButton) {
                submitButton.disabled = false;
                submitButton.removeAttribute("aria-busy");
            }

            if (submitLabel) {
                submitLabel.textContent =
                    currentMode === "signup" ? "Create Account" : "Log In";
            }
        }
    }

    function setupPasswordToggle(button, input) {
        if (!button || !input) return;

        button.addEventListener("click", () => {
            const shouldShow = input.type === "password";

            input.type = shouldShow ? "text" : "password";
            button.textContent = shouldShow ? "Hide" : "Show";

            button.setAttribute(
                "aria-label",
                shouldShow ? "Hide password" : "Show password"
            );
        });
    }

    if (loginTab) {
        loginTab.addEventListener("click", () => switchMode("login"));
    }

    if (signupTab) {
        signupTab.addEventListener("click", () => switchMode("signup"));
    }

    if (form) {
        form.addEventListener("submit", handleSubmit);
    }

    setupPasswordToggle(togglePassword, passwordInput);
    setupPasswordToggle(toggleConfirmPassword, confirmPasswordInput);

    // Start on the login page.
    switchMode("login");
});
