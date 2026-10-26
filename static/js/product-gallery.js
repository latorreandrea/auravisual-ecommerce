/**
 * Product card side gallery.
 *
 * The first side is server-rendered and visible without JavaScript. This
 * controller enhances each card with looping navigation, a desktop hover
 * autoplay, keyboard controls and touch swiping. Clones of the first and last
 * slides make the loop continuous; they are hidden from assistive technology.
 */
(function () {
  "use strict";

  const AUTOPLAY_DELAY = 1500;
  const HOVER_START_DELAY = 320;
  const LEAVE_RESET_DELAY = 600;
  const TRANSITION_MS = 450;
  const SWIPE_THRESHOLD = 44;

  const hoverCapable = window.matchMedia("(hover: hover) and (pointer: fine)");
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function initCard(card) {
    const gallery = card.querySelector("[data-product-gallery]");
    if (!gallery || gallery.dataset.galleryReady === "true") {
      return;
    }

    const viewport = gallery.querySelector("[data-gallery-viewport]");
    const track = gallery.querySelector("[data-gallery-track]");
    const originals = Array.from(
      gallery.querySelectorAll("[data-gallery-slide]")
    );
    if (!viewport || !track || originals.length === 0) {
      return;
    }

    gallery.dataset.galleryReady = "true";

    const prevButton = gallery.querySelector("[data-gallery-prev]");
    const nextButton = gallery.querySelector("[data-gallery-next]");
    const dots = Array.from(gallery.querySelectorAll("[data-gallery-dot]"));
    const label = gallery.querySelector("[data-gallery-label]");
    const counter = gallery.querySelector("[data-gallery-count]");
    const status = gallery.querySelector("[data-gallery-status]");
    const total = originals.length;

    let position = 0;
    let realIndex = 0;
    let clonesReady = false;
    let isTransitioning = false;
    let isHovering = false;
    let manualPause = false;
    let isDragging = false;
    let dragStartX = 0;
    let dragDelta = 0;
    let activePointerId = null;
    let autoplayTimer = null;
    let startTimer = null;
    let resetTimer = null;
    let normalizeTimer = null;

    function setTransform(animate, offset) {
      const offsetValue = typeof offset === "number" ? offset : 0;
      const translate = offsetValue === 0
        ? `${-position * 100}%`
        : `calc(${-position * 100}% ${offsetValue < 0 ? "-" : "+"} ${Math.abs(offsetValue)}px)`;

      track.style.transition =
        animate && !reduceMotion.matches
          ? `transform ${TRANSITION_MS}ms cubic-bezier(0.22, 0.61, 0.36, 1)`
          : "none";
      track.style.transform = `translate3d(${translate}, 0, 0)`;
    }

    function ensureClones() {
      if (clonesReady || total < 2) {
        return;
      }

      const firstClone = originals[0].cloneNode(true);
      const lastClone = originals[total - 1].cloneNode(true);

      [firstClone, lastClone].forEach(function (clone) {
        clone.removeAttribute("data-gallery-slide");
        clone.removeAttribute("role");
        clone.removeAttribute("aria-roledescription");
        clone.removeAttribute("aria-label");
        clone.setAttribute("aria-hidden", "true");
        clone.querySelectorAll("img").forEach(function (image) {
          image.alt = "";
          image.loading = "lazy";
        });
      });

      track.prepend(lastClone);
      track.append(firstClone);
      clonesReady = true;
      position = 1;
      setTransform(false);
    }

    function updateUi(announce) {
      const activeSlide = originals[realIndex];
      if (!activeSlide) {
        return;
      }

      originals.forEach(function (slide, index) {
        if (index === realIndex) {
          slide.removeAttribute("aria-hidden");
        } else {
          slide.setAttribute("aria-hidden", "true");
        }
      });

      dots.forEach(function (dot, index) {
        if (index === realIndex) {
          dot.setAttribute("aria-current", "true");
        } else {
          dot.removeAttribute("aria-current");
        }
      });

      const name = activeSlide.getAttribute("data-gallery-name") || "Side";
      if (label) {
        label.textContent = name;
      }
      if (counter) {
        counter.textContent = `${realIndex + 1} / ${total}`;
      }
      if (announce && status) {
        status.textContent = `${name}, ${realIndex + 1} of ${total}`;
      }
    }

    function clearNormalizeTimer() {
      if (normalizeTimer !== null) {
        window.clearTimeout(normalizeTimer);
        normalizeTimer = null;
      }
    }

    function normalizeAfterLoop() {
      clearNormalizeTimer();
      normalizeTimer = window.setTimeout(function () {
        normalizeTimer = null;
        isTransitioning = false;
        if (!clonesReady) {
          return;
        }
        if (position === total + 1) {
          position = 1;
          setTransform(false);
        } else if (position === 0) {
          position = total;
          setTransform(false);
        }
      }, TRANSITION_MS + 40);
    }

    function moveTo(targetPosition, animate, announce) {
      if (total < 2) {
        return;
      }

      ensureClones();
      let nextPosition = targetPosition;
      if (!animate) {
        if (nextPosition === total + 1) {
          nextPosition = 1;
        } else if (nextPosition === 0) {
          nextPosition = total;
        }
      }

      position = nextPosition;
      setTransform(animate);
      updateUi(announce);

      if (animate && !reduceMotion.matches) {
        isTransitioning = true;
        normalizeAfterLoop();
      } else {
        isTransitioning = false;
      }
    }

    function moveBy(direction, announce) {
      if (total < 2 || isTransitioning) {
        return;
      }

      ensureClones();
      realIndex = (realIndex + direction + total) % total;
      moveTo(position + direction, true, announce);
    }

    function goToReal(index, announce) {
      if (total < 2 || isTransitioning) {
        return;
      }

      ensureClones();
      if (index === realIndex) {
        return;
      }

      realIndex = index;
      moveTo(index + 1, true, announce);
    }

    function resetToFirst() {
      if (isDragging) {
        return;
      }

      clearNormalizeTimer();
      isTransitioning = false;
      realIndex = 0;
      position = clonesReady ? 1 : 0;
      setTransform(false);
      updateUi(false);
    }

    function canAutoplay() {
      return (
        total > 1 &&
        hoverCapable.matches &&
        !reduceMotion.matches &&
        isHovering &&
        !manualPause &&
        !isDragging &&
        !document.hidden &&
        !hasKeyboardFocus()
      );
    }

    function stopAutoplay() {
      if (autoplayTimer !== null) {
        window.clearInterval(autoplayTimer);
        autoplayTimer = null;
      }
    }

    function clearStartTimer() {
      if (startTimer !== null) {
        window.clearTimeout(startTimer);
        startTimer = null;
      }
    }

    function clearResetTimer() {
      if (resetTimer !== null) {
        window.clearTimeout(resetTimer);
        resetTimer = null;
      }
    }

    function startAutoplay() {
      stopAutoplay();
      if (!canAutoplay()) {
        return;
      }

      ensureClones();
      autoplayTimer = window.setInterval(function () {
        if (canAutoplay() && !isTransitioning) {
          moveBy(1, false);
        }
      }, AUTOPLAY_DELAY);
    }

    function scheduleAutoplay(delay) {
      clearStartTimer();
      startTimer = window.setTimeout(function () {
        startTimer = null;
        startAutoplay();
      }, delay);
    }

    function pauseAutoplayForInteraction() {
      manualPause = true;
      stopAutoplay();
      clearStartTimer();
    }

    function animateSnapBack() {
      setTransform(true);
      if (reduceMotion.matches) {
        isTransitioning = false;
      } else {
        isTransitioning = true;
        normalizeAfterLoop();
      }
      if (isHovering) {
        scheduleAutoplay(HOVER_START_DELAY);
      }
    }

    function finishDrag(commit) {
      if (!isDragging) {
        return;
      }

      const delta = dragDelta;
      const pointerId = activePointerId;
      isDragging = false;
      activePointerId = null;
      dragDelta = 0;
      track.classList.remove("is-dragging");

      if (pointerId !== null && viewport.releasePointerCapture) {
        try {
          viewport.releasePointerCapture(pointerId);
        } catch (error) {
          // The pointer may already have been released by the browser.
        }
      }

      if (commit && Math.abs(delta) >= SWIPE_THRESHOLD) {
        pauseAutoplayForInteraction();
        moveBy(delta < 0 ? 1 : -1, true);
      } else {
        animateSnapBack();
      }
    }

    function hasKeyboardFocus() {
      const active = document.activeElement;
      if (!active || !card.contains(active)) {
        return false;
      }
      if (typeof active.matches !== "function") {
        return true;
      }
      try {
        return active.matches(":focus-visible");
      } catch (error) {
        // Older browsers without :focus-visible stay conservative.
        return true;
      }
    }

    gallery.classList.add("is-enhanced");
    updateUi(false);
    setTransform(false);

    if (total < 2) {
      return;
    }

    if (prevButton) {
      prevButton.addEventListener("click", function () {
        pauseAutoplayForInteraction();
        moveBy(-1, true);
      });
    }

    if (nextButton) {
      nextButton.addEventListener("click", function () {
        pauseAutoplayForInteraction();
        moveBy(1, true);
      });
    }

    dots.forEach(function (dot) {
      dot.addEventListener("click", function () {
        const index = Number.parseInt(
          dot.getAttribute("data-gallery-dot") || "",
          10
        );
        if (Number.isNaN(index)) {
          return;
        }
        pauseAutoplayForInteraction();
        goToReal(index, true);
      });
    });

    gallery.addEventListener("keydown", function (event) {
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        pauseAutoplayForInteraction();
        moveBy(-1, true);
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        pauseAutoplayForInteraction();
        moveBy(1, true);
      } else if (event.key === "Home") {
        event.preventDefault();
        pauseAutoplayForInteraction();
        goToReal(0, true);
      } else if (event.key === "End") {
        event.preventDefault();
        pauseAutoplayForInteraction();
        goToReal(total - 1, true);
      }
    });

    card.addEventListener("mouseenter", function () {
      if (!hoverCapable.matches) {
        return;
      }
      isHovering = true;
      manualPause = false;
      clearResetTimer();
      scheduleAutoplay(HOVER_START_DELAY);
    });

    card.addEventListener("mouseleave", function () {
      if (!hoverCapable.matches) {
        return;
      }
      isHovering = false;
      stopAutoplay();
      clearStartTimer();
      if (card.matches(":focus-within")) {
        return;
      }
      clearResetTimer();
      resetTimer = window.setTimeout(function () {
        resetTimer = null;
        if (!isHovering && !card.matches(":focus-within")) {
          resetToFirst();
        }
      }, LEAVE_RESET_DELAY);
    });

    card.addEventListener("focusin", function () {
      stopAutoplay();
      clearStartTimer();
      clearResetTimer();
    });

    card.addEventListener("focusout", function (event) {
      if (card.contains(event.relatedTarget)) {
        return;
      }
      if (isHovering && hoverCapable.matches) {
        scheduleAutoplay(HOVER_START_DELAY);
      } else if (!isHovering) {
        resetToFirst();
      }
    });

    viewport.addEventListener("pointerdown", function (event) {
      if (event.pointerType === "mouse") {
        return;
      }

      ensureClones();
      clearNormalizeTimer();
      isTransitioning = false;
      if (position === total + 1) {
        position = 1;
      } else if (position === 0) {
        position = total;
      }
      setTransform(false);

      stopAutoplay();
      clearStartTimer();
      clearResetTimer();
      isDragging = true;
      activePointerId = event.pointerId;
      dragStartX = event.clientX;
      dragDelta = 0;
      track.classList.add("is-dragging");

      if (viewport.setPointerCapture) {
        try {
          viewport.setPointerCapture(event.pointerId);
        } catch (error) {
          // Pointer capture is optional; pointerup still completes the swipe.
        }
      }
    });

    viewport.addEventListener("pointermove", function (event) {
      if (!isDragging || event.pointerId !== activePointerId) {
        return;
      }

      const width = viewport.clientWidth || 1;
      dragDelta = clamp(
        event.clientX - dragStartX,
        -width * 0.65,
        width * 0.65
      );
      setTransform(false, dragDelta);
    });

    viewport.addEventListener("pointerup", function (event) {
      if (!isDragging || event.pointerId !== activePointerId) {
        return;
      }
      finishDrag(true);
    });

    viewport.addEventListener("pointercancel", function (event) {
      if (!isDragging || event.pointerId !== activePointerId) {
        return;
      }
      finishDrag(false);
    });

    viewport.addEventListener("lostpointercapture", function (event) {
      if (!isDragging || event.pointerId !== activePointerId) {
        return;
      }
      finishDrag(false);
    });

    viewport.addEventListener("pointerleave", function (event) {
      if (!isDragging || event.pointerId !== activePointerId) {
        return;
      }
      const hasCapture =
        viewport.hasPointerCapture &&
        viewport.hasPointerCapture(event.pointerId);
      if (!hasCapture) {
        finishDrag(false);
      }
    });

    document.addEventListener("visibilitychange", function () {
      if (document.hidden) {
        stopAutoplay();
        clearStartTimer();
      } else if (isHovering) {
        scheduleAutoplay(HOVER_START_DELAY);
      }
    });

    if (reduceMotion.addEventListener) {
      reduceMotion.addEventListener("change", function () {
        if (reduceMotion.matches) {
          stopAutoplay();
          clearStartTimer();
          resetToFirst();
        } else if (isHovering) {
          scheduleAutoplay(HOVER_START_DELAY);
        }
      });
    }

    if (hoverCapable.addEventListener) {
      hoverCapable.addEventListener("change", function () {
        if (!hoverCapable.matches) {
          isHovering = false;
          stopAutoplay();
          clearStartTimer();
          clearResetTimer();
        }
      });
    }
  }

  function initAll() {
    document.querySelectorAll("[data-product-card]").forEach(initCard);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }
})();
