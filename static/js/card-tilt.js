(() => {
    "use strict";

    const cards = Array.from(document.querySelectorAll("[data-tilt]"));
    if (!cards.length || typeof window.VanillaTilt === "undefined") {
        return;
    }

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (reduceMotion.matches) {
        return;
    }

    function settingsFor(card, gyroscope) {
        return {
            max: Number(card.dataset.tiltMax) || 12,
            speed: Number(card.dataset.tiltSpeed) || 600,
            scale: Number(card.dataset.tiltScale) || 1,
            // No glare: the overlay also lit the transparent padding around
            // the contained mockup, which detached the card from the panel.
            glare: false,
            gyroscope: gyroscope,
            "gyroscope-min-angle-x": -45,
            "gyroscope-max-angle-x": 45,
            "gyroscope-min-angle-y": -45,
            "gyroscope-max-angle-y": 45,
        };
    }

    function start(gyroscope) {
        cards.forEach((card) => {
            if (card.vanillaTilt) {
                card.vanillaTilt.destroy();
            }
            window.VanillaTilt.init(card, settingsFor(card, gyroscope));
        });
    }

    // iOS 13+ only grants motion access from a user gesture.
    const needsPermission =
        typeof window.DeviceOrientationEvent !== "undefined" &&
        typeof window.DeviceOrientationEvent.requestPermission === "function";

    if (!needsPermission) {
        start(true);
        return;
    }

    // Pointer tilt works immediately; the gyroscope needs an explicit tap.
    start(false);

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "tilt-motion-btn";
    toggle.dataset.motionToggle = "1";
    toggle.innerHTML =
        '<i class="bi bi-phone" aria-hidden="true"></i>Tilt with your phone';

    const host = document.querySelector(".home-hero-visual") || cards[0].parentElement;
    if (host) {
        host.appendChild(toggle);
    }

    toggle.addEventListener("click", async () => {
        try {
            const response = await window.DeviceOrientationEvent.requestPermission();
            if (response === "granted") {
                start(true);
                toggle.remove();
                return;
            }
            toggle.textContent = "Motion access was denied";
        } catch (error) {
            toggle.textContent = "Motion is not available";
        }
    });
})();
