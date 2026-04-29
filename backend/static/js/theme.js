(() => {
    const THEME_KEY = "theme";
    const LEGACY_THEME_KEY = "fuelguard-theme";
    const root = document.documentElement;
    const body = document.body;

    if (!root || !body) return;

    const validTheme = (value) => (value === "dark" ? "dark" : "light");

    const applyTheme = (theme) => {
        const next = validTheme(theme);
        root.setAttribute("data-theme", next);
        body.classList.remove("light-mode", "dark-mode");
        body.classList.add(next === "dark" ? "dark-mode" : "light-mode");
        localStorage.setItem(THEME_KEY, next);
        localStorage.setItem(LEGACY_THEME_KEY, next);
        updateToggleLabel(next);
    };

    const updateToggleLabel = (theme) => {
        const btn = document.querySelector("[data-theme-toggle]");
        if (!btn) return;
        btn.textContent = theme === "dark" ? "🌙" : "☀️";
        btn.setAttribute(
            "aria-label",
            theme === "dark" ? "Dark Mode active" : "Light Mode active"
        );
        btn.setAttribute("title", theme === "dark" ? "Dark Mode" : "Light Mode");
    };

    const ensureToggle = () => {
        let btn = document.querySelector("[data-theme-toggle]");
        if (btn) return btn;

        btn = document.createElement("button");
        btn.type = "button";
        btn.className = "theme-toggle";
        btn.setAttribute("data-theme-toggle", "true");
        btn.setAttribute("aria-label", "Light Mode active");
        btn.textContent = "☀️";
        body.appendChild(btn);
        return btn;
    };

    const saved = localStorage.getItem(THEME_KEY) || localStorage.getItem(LEGACY_THEME_KEY);
    if (saved) {
        applyTheme(validTheme(saved));
    } else if (!root.getAttribute("data-theme")) {
        applyTheme("light");
    } else {
        applyTheme(validTheme(root.getAttribute("data-theme")));
    }

    const toggleBtn = ensureToggle();
    updateToggleLabel(validTheme(root.getAttribute("data-theme")));
    toggleBtn.addEventListener("click", () => {
        const current = root.getAttribute("data-theme");
        applyTheme(current === "dark" ? "light" : "dark");
    });
})();
