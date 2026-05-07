(() => {
    const THEME_KEY = "theme";
    const LEGACY_THEME_KEY = "fuelguard-theme";
    const AUTH_REV_KEY = "fg_auth_rev";
    const root = document.documentElement;
    const body = document.body;

    if (!root || !body) return;

    const bumpAuthRevision = () => {
        try {
            localStorage.setItem(AUTH_REV_KEY, String(Date.now()));
        } catch (_) {
            /* ignore */
        }
    };

    const stripAuthSyncQuery = () => {
        try {
            const u = new URL(window.location.href);
            const sync = u.searchParams.get("fg_auth_sync");
            if (!sync) return;
            u.searchParams.delete("fg_auth_sync");
            const next = u.pathname + (u.search ? u.search : "") + u.hash;
            window.history.replaceState(null, "", next);
            if (sync === "logout" || sync === "1") {
                bumpAuthRevision();
            }
        } catch (_) {
            /* ignore */
        }
    };

    stripAuthSyncQuery();

    /** Move header controls into one flex row with a slot for the theme control (left of Logout / actions). */
    const mountDashHeaderActions = () => {
        document.querySelectorAll("header.dash-top:not([data-theme-actions-mounted])").forEach((header) => {
            const titleGroup = header.querySelector(":scope > .title-group");
            const children = Array.from(header.children).filter((el) => el !== titleGroup);
            const wrap = document.createElement("div");
            wrap.className = "dash-header-actions";
            const host = document.createElement("span");
            host.className = "theme-toggle-host";
            host.setAttribute("data-theme-toggle-host", "");
            wrap.appendChild(host);
            children.forEach((el) => {
                header.removeChild(el);
                wrap.appendChild(el);
            });
            header.appendChild(wrap);
            header.setAttribute("data-theme-actions-mounted", "true");
        });
    };

    mountDashHeaderActions();

    const validTheme = (value) => (value === "dark" ? "dark" : "light");

    const applyTheme = (theme) => {
        const next = validTheme(theme);
        root.setAttribute("data-theme", next);
        body.classList.remove("light-mode", "dark-mode");
        body.classList.add(next === "dark" ? "dark-mode" : "light-mode");
        try {
            sessionStorage.setItem(THEME_KEY, next);
            sessionStorage.setItem(LEGACY_THEME_KEY, next);
        } catch (_) {
            /* ignore */
        }
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
        btn.setAttribute("data-theme-toggle", "true");
        btn.setAttribute("aria-label", "Light Mode active");
        btn.textContent = "☀️";
        const host = document.querySelector("[data-theme-toggle-host]");
        if (host) {
            btn.className = "theme-toggle theme-toggle--inline";
            host.appendChild(btn);
        } else {
            btn.className = "theme-toggle theme-toggle--floating";
            body.appendChild(btn);
        }
        return btn;
    };

    let saved = null;
    try {
        saved =
            sessionStorage.getItem(THEME_KEY) ||
            sessionStorage.getItem(LEGACY_THEME_KEY);
    } catch (_) {
        saved = null;
    }
    if (!saved) {
        try {
            saved =
                localStorage.getItem(THEME_KEY) ||
                localStorage.getItem(LEGACY_THEME_KEY);
            if (saved) {
                try {
                    sessionStorage.setItem(THEME_KEY, saved);
                    sessionStorage.setItem(LEGACY_THEME_KEY, saved);
                } catch (_) {
                    /* ignore */
                }
            }
        } catch (_) {
            saved = null;
        }
    }

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

(() => {
    const DISPLAY_MS = 30000;
    const FADE_MS = 400;

    const fadeOutRemove = (el) => {
        if (!el || !el.isConnected) return;
        el.style.transition = `opacity ${FADE_MS}ms ease`;
        el.style.opacity = "0";
        setTimeout(() => el.remove(), FADE_MS);
    };

    const scheduleDismissals = () => {
        document.querySelectorAll("ul.flash-list:not([data-fg-notification-sticky])").forEach((el) => {
            setTimeout(() => fadeOutRemove(el), DISPLAY_MS);
        });
        document.querySelectorAll("[data-fg-notification-panel]:not([data-fg-notification-sticky])").forEach((el) => {
            setTimeout(() => fadeOutRemove(el), DISPLAY_MS);
        });
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", scheduleDismissals);
    } else {
        scheduleDismissals();
    }
})();
