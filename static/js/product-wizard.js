(() => {
    "use strict";

    const form = document.getElementById("product-wizard-form");
    if (!form) {
        return;
    }

    const stepPanels = Array.from(form.querySelectorAll("[data-wizard-step]"));
    const stepIndicators = Array.from(
        form.querySelectorAll("[data-step-indicator]")
    );
    const progressBar = form.querySelector("[data-wizard-progress]");
    const progressRegion = form.querySelector(".wizard-progress");
    const facePanelsContainer = form.querySelector("[data-face-panels]");
    const tabsNode = form.querySelector("[data-face-tabs]");
    const addFaceButton = form.querySelector("[data-add-face]");
    const faceTemplate = document.getElementById("wizard-face-template");
    const totalFormsInput = form.querySelector('input[name="views-TOTAL_FORMS"]');
    const maxFormsInput = form.querySelector('input[name="views-MAX_NUM_FORMS"]');
    const minFormsInput = form.querySelector('input[name="views-MIN_NUM_FORMS"]');
    const globalError = document.getElementById("wizard-error");
    const submitButton = document.getElementById("wizard-submit");
    const submitLabel = form.querySelector("[data-submit-label]");
    const submitSpinner = form.querySelector("[data-submit-spinner]");

    if (
        !stepPanels.length ||
        !facePanelsContainer ||
        !tabsNode ||
        !totalFormsInput ||
        !faceTemplate
    ) {
        return;
    }

    const MIN_RATIO = 0.01;
    const DEFAULT_RATIOS = {
        x: 0.1,
        y: 0.1,
        width: 0.8,
        height: 0.8,
    };
    const maxFaces = Math.max(
        1,
        parseInt(maxFormsInput?.value || form.dataset.maxViews || "8", 10) || 8
    );
    let currentStep = clamp(
        parseInt(form.dataset.initialStep || "1", 10) || 1,
        1,
        3
    );
    let activeFace = Math.max(
        0,
        parseInt(form.dataset.initialFace || "0", 10) || 0
    );
    let maxVisitedStep = currentStep;
    let submitBusy = false;
    const faceState = new WeakMap();

    form.noValidate = true;
    if (minFormsInput) {
        minFormsInput.value = "1";
    }

    function clamp(value, minimum, maximum) {
        return Math.min(Math.max(value, minimum), maximum);
    }

    function round(value, decimals = 6) {
        const factor = 10 ** decimals;
        return Math.round(value * factor) / factor;
    }

    function formatPercent(ratio) {
        return (ratio * 100).toFixed(1).replace(/\.0$/, "");
    }

    function formatBytes(bytes) {
        if (!bytes) {
            return "0 MB";
        }
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    }

    function panels() {
        return Array.from(
            facePanelsContainer.querySelectorAll("[data-face-panel]")
        );
    }

    function panelAt(index) {
        return panels()[index] || null;
    }

    function faceFields(panel) {
        return {
            name: panel.querySelector('[name^="views-"][name$="-name"]'),
            file: panel.querySelector('input[type="file"][name$="-mockup_image"]'),
            zoneName: panel.querySelector('[name^="zone-"][name$="-name"]'),
            fullFace: panel.querySelector(
                'input[type="checkbox"][name^="zone-"][name$="-full_face"]'
            ),
            x: panel.querySelector('[name^="zone-"][name$="-x_ratio"]'),
            y: panel.querySelector('[name^="zone-"][name$="-y_ratio"]'),
            width: panel.querySelector('[name^="zone-"][name$="-width_ratio"]'),
            height: panel.querySelector('[name^="zone-"][name$="-height_ratio"]'),
            stage: panel.querySelector("[data-area-stage]"),
            image: panel.querySelector("[data-mockup-preview]"),
            placeholder: panel.querySelector("[data-stage-placeholder]"),
            hint: panel.querySelector("[data-stage-hint]"),
            areaBox: panel.querySelector("[data-area-box]"),
            areaMode: panel.querySelector("[data-area-mode]"),
            areaError: panel.querySelector("[data-area-error]"),
            fileName: panel.querySelector("[data-file-name]"),
        };
    }

    function defaultFaceName(index) {
        if (index === 0) {
            return "Front";
        }
        if (index === 1) {
            return "Back";
        }
        return `Side ${index + 1}`;
    }

    function readRatios(panel) {
        const fields = faceFields(panel);
        const parsed = {};
        ["x", "y", "width", "height"].forEach((key) => {
            const value = parseFloat(fields[key]?.value || "");
            parsed[key] = Number.isFinite(value) ? value : DEFAULT_RATIOS[key];
        });
        parsed.x = clamp(parsed.x, 0, 1 - MIN_RATIO);
        parsed.y = clamp(parsed.y, 0, 1 - MIN_RATIO);
        parsed.width = clamp(parsed.width, MIN_RATIO, 1);
        parsed.height = clamp(parsed.height, MIN_RATIO, 1);
        if (parsed.x + parsed.width > 1) {
            parsed.width = Math.max(MIN_RATIO, 1 - parsed.x);
        }
        if (parsed.y + parsed.height > 1) {
            parsed.height = Math.max(MIN_RATIO, 1 - parsed.y);
        }
        return parsed;
    }

    function writeRatios(panel, ratios) {
        const fields = faceFields(panel);
        const next = {
            x: clamp(ratios.x, 0, 1 - MIN_RATIO),
            y: clamp(ratios.y, 0, 1 - MIN_RATIO),
            width: clamp(ratios.width, MIN_RATIO, 1),
            height: clamp(ratios.height, MIN_RATIO, 1),
        };
        next.width = Math.max(MIN_RATIO, Math.min(next.width, 1 - next.x));
        next.height = Math.max(MIN_RATIO, Math.min(next.height, 1 - next.y));
        ["x", "y", "width", "height"].forEach((key) => {
            if (fields[key]) {
                fields[key].value = String(round(next[key]));
            }
        });
        return next;
    }

    function syncArea(panel) {
        const fields = faceFields(panel);
        const hasImage = Boolean(
            fields.image && !fields.image.hidden && fields.image.getAttribute("src")
        );
        const fullFace = Boolean(fields.fullFace?.checked);

        if (fields.areaBox) {
            fields.areaBox.hidden = !hasImage;
            fields.areaBox.classList.toggle("is-full-face", fullFace);
        }
        if (fields.stage) {
            fields.stage.classList.toggle("is-editable", hasImage);
        }
        if (fields.hint) {
            fields.hint.hidden =
                !hasImage || panel.dataset.hintDismissed === "true";
        }

        let ratios = readRatios(panel);
        if (fullFace) {
            ratios = { x: 0, y: 0, width: 1, height: 1 };
        }

        if (hasImage && fields.areaBox) {
            fields.areaBox.style.left = `${ratios.x * 100}%`;
            fields.areaBox.style.top = `${ratios.y * 100}%`;
            fields.areaBox.style.width = `${ratios.width * 100}%`;
            fields.areaBox.style.height = `${ratios.height * 100}%`;
            fields.areaBox.setAttribute(
                "aria-label",
                `Printable area: left ${formatPercent(ratios.x)}%, ` +
                    `top ${formatPercent(ratios.y)}%, ` +
                    `width ${formatPercent(ratios.width)}%, ` +
                    `height ${formatPercent(ratios.height)}%`
            );
        }

        if (fields.areaMode) {
            fields.areaMode.textContent = fullFace
                ? "Entire face"
                : "Custom rectangle";
        }

        panel.querySelectorAll("[data-area-input]").forEach((input) => {
            const key = input.dataset.areaInput;
            input.disabled = fullFace || !hasImage;
            if (document.activeElement !== input) {
                input.value = formatPercent(ratios[key]);
            }
        });
    }


    function updateTabLabels() {
        panels().forEach((panel, index) => {
            const fields = faceFields(panel);
            const name = (fields.name?.value || defaultFaceName(index)).trim();
            const label = tabsNode.querySelector(
                `[data-face-tab="${index}"] .wizard-face-tab-label`
            );
            if (label) {
                label.textContent = name || defaultFaceName(index);
            }
            const display = panel.querySelector("[data-face-display-name]");
            if (display) {
                display.textContent = name || defaultFaceName(index);
            }
            const tab = tabsNode.querySelector(`[data-face-tab="${index}"]`);
            if (tab) {
                tab.setAttribute(
                    "aria-label",
                    `Edit ${name || defaultFaceName(index)}`
                );
            }
        });
    }

    function updateAddState() {
        const count = panels().length;
        if (addFaceButton) {
            addFaceButton.hidden = false;
            addFaceButton.disabled = count >= maxFaces;
            addFaceButton.title =
                count >= maxFaces
                    ? `A product can have at most ${maxFaces} sides.`
                    : "";
        }
        tabsNode.hidden = count === 0;
    }

    function setActiveFace(index) {
        const allPanels = panels();
        if (!allPanels.length) {
            activeFace = 0;
            return;
        }
        activeFace = clamp(index, 0, allPanels.length - 1);
        allPanels.forEach((panel, panelIndex) => {
            const isActive = panelIndex === activeFace;
            panel.hidden = !isActive;
            panel.classList.toggle("is-active", isActive);
        });
        tabsNode.querySelectorAll("[data-face-tab]").forEach((tab) => {
            const isActive = Number(tab.dataset.faceTab) === activeFace;
            tab.setAttribute("aria-selected", isActive ? "true" : "false");
            tab.tabIndex = isActive ? 0 : -1;
            tab.closest(".wizard-face-tab-item")?.classList.toggle(
                "is-active",
                isActive
            );
        });
    }

    function showStep(step, options = {}) {
        currentStep = clamp(step, 1, 3);
        maxVisitedStep = Math.max(maxVisitedStep, currentStep);

        stepPanels.forEach((panel) => {
            const panelStep = Number(panel.dataset.wizardStep);
            const isActive = panelStep === currentStep;
            panel.hidden = !isActive;
            panel.classList.toggle("is-active", isActive);
        });

        stepIndicators.forEach((indicator) => {
            const indicatorStep = Number(indicator.dataset.stepIndicator);
            const button = indicator.querySelector("button");
            indicator.classList.toggle(
                "is-current",
                indicatorStep === currentStep
            );
            indicator.classList.toggle(
                "is-complete",
                indicatorStep < currentStep
            );
            if (button) {
                if (indicatorStep === currentStep) {
                    button.setAttribute("aria-current", "step");
                } else {
                    button.removeAttribute("aria-current");
                }
                button.disabled =
                    indicatorStep > maxVisitedStep &&
                    indicatorStep !== currentStep;
            }
        });

        if (progressBar) {
            progressBar.style.width = `${(currentStep / 3) * 100}%`;
        }
        if (progressRegion) {
            progressRegion.setAttribute(
                "aria-valuenow",
                String(Math.round((currentStep / 3) * 100))
            );
        }

        if (options.focus !== false) {
            const top = form.getBoundingClientRect().top + window.scrollY - 96;
            window.scrollTo({
                top: Math.max(top, 0),
                behavior: window.matchMedia("(prefers-reduced-motion: reduce)")
                    .matches
                    ? "auto"
                    : "smooth",
            });
        }
    }


    function stateFor(panel) {
        let state = faceState.get(panel);
        if (!state) {
            state = { previewUrl: "", lastCustom: null };
            faceState.set(panel, state);
        }
        return state;
    }

    function revokePreview(panel) {
        const state = stateFor(panel);
        if (state.previewUrl) {
            URL.revokeObjectURL(state.previewUrl);
            state.previewUrl = "";
        }
    }

    function resetStageSize(panel) {
        const fields = faceFields(panel);
        if (!fields.stage) {
            return;
        }
        fields.stage.style.aspectRatio = "4 / 3";
        fields.stage.style.removeProperty("--stage-max-width");
    }

    function fitStage(panel) {
        const fields = faceFields(panel);
        const image = fields.image;
        if (!fields.stage || !image || image.hidden) {
            return;
        }
        const width = image.naturalWidth || 0;
        const height = image.naturalHeight || 0;
        if (!width || !height) {
            return;
        }

        const viewportHeight =
            window.visualViewport?.height || window.innerHeight || 720;
        const maxHeight = Math.min(viewportHeight * 0.62, 620);
        const maxWidth = Math.max(1, Math.round((maxHeight * width) / height));

        fields.stage.style.aspectRatio = `${width} / ${height}`;
        fields.stage.style.setProperty("--stage-max-width", `${maxWidth}px`);
    }

    let stageFitFrame = 0;

    function scheduleStageFit() {
        if (stageFitFrame) {
            return;
        }
        stageFitFrame = window.requestAnimationFrame(() => {
            stageFitFrame = 0;
            panels().forEach(fitStage);
        });
    }

    function clearPreview(panel) {
        const fields = faceFields(panel);
        revokePreview(panel);
        delete panel.dataset.hintDismissed;
        if (fields.image) {
            fields.image.onload = null;
            fields.image.onerror = null;
            fields.image.hidden = true;
            fields.image.removeAttribute("src");
        }
        if (fields.placeholder) {
            fields.placeholder.hidden = false;
        }
        resetStageSize(panel);
        if (fields.fileName) {
            fields.fileName.textContent = "No image selected";
        }
        syncArea(panel);
    }

    function loadPreview(panel) {
        const fields = faceFields(panel);
        const file = fields.file?.files?.[0];
        if (!file) {
            clearPreview(panel);
            rebuildTabs();
            return;
        }

        const state = stateFor(panel);
        revokePreview(panel);
        delete panel.dataset.hintDismissed;
        const url = URL.createObjectURL(file);
        state.previewUrl = url;

        if (fields.fileName) {
            fields.fileName.textContent = `${file.name} (${formatBytes(file.size)})`;
        }
        if (fields.placeholder) {
            fields.placeholder.hidden = true;
        }
        if (fields.image) {
            fields.image.hidden = true;
            fields.image.onload = () => {
                fields.image.hidden = false;
                fitStage(panel);
                syncArea(panel);
                rebuildTabs();
            };
            fields.image.onerror = () => {
                fields.image.hidden = true;
                if (fields.placeholder) {
                    fields.placeholder.hidden = false;
                }
                resetStageSize(panel);
                if (fields.fileName) {
                    fields.fileName.textContent =
                        "The selected image could not be previewed.";
                }
                syncArea(panel);
            };
            fields.image.src = url;
        }
        syncArea(panel);
        updateTabLabels();
    }


    function toolButton(action, icon, label, disabled) {
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.faceAction = action;
        button.setAttribute("aria-label", label);
        button.title = label;
        button.disabled = Boolean(disabled);
        const glyph = document.createElement("i");
        glyph.className = `bi ${icon}`;
        glyph.setAttribute("aria-hidden", "true");
        button.append(glyph);
        return button;
    }

    function rebuildTabs() {
        const allPanels = panels();
        tabsNode.textContent = "";

        allPanels.forEach((panel, index) => {
            const fields = faceFields(panel);
            const name = (fields.name?.value || defaultFaceName(index)).trim();
            const item = document.createElement("div");
            item.className = "wizard-face-tab-item";

            const tab = document.createElement("button");
            tab.type = "button";
            tab.className = "wizard-face-tab";
            tab.id = `wizard-face-tab-${index}`;
            tab.dataset.faceTab = String(index);
            tab.setAttribute("role", "tab");
            tab.setAttribute("aria-selected", "false");
            tab.setAttribute("aria-controls", `face-panel-${index}`);
            tab.setAttribute(
                "aria-label",
                `Edit ${name || defaultFaceName(index)}`
            );
            panel.setAttribute("aria-labelledby", tab.id);

            const thumb = document.createElement("span");
            thumb.className = "wizard-face-thumb";
            thumb.setAttribute("aria-hidden", "true");
            const preview = fields.image?.getAttribute("src");
            if (preview && !fields.image.hidden) {
                thumb.classList.add("has-image");
                thumb.style.backgroundImage = `url("${preview}")`;
            }

            const label = document.createElement("span");
            label.className = "wizard-face-tab-label";
            label.textContent = name || defaultFaceName(index);

            tab.append(thumb, label);

            const tools = document.createElement("div");
            tools.className = "wizard-face-tab-tools";
            tools.append(
                toolButton(
                    "up",
                    "bi-arrow-left",
                    `Move ${name || defaultFaceName(index)} left`,
                    index === 0
                ),
                toolButton(
                    "down",
                    "bi-arrow-right",
                    `Move ${name || defaultFaceName(index)} right`,
                    index === allPanels.length - 1
                ),
                toolButton(
                    "remove",
                    "bi-x-lg",
                    `Remove ${name || defaultFaceName(index)}`,
                    allPanels.length <= 1
                )
            );

            item.append(tab, tools);
            tabsNode.append(item);
        });

        tabsNode.hidden = allPanels.length === 0;
        setActiveFace(activeFace);
    }

    function reindexFaces() {
        const allPanels = panels();
        allPanels.forEach((panel, index) => {
            panel.dataset.faceIndex = String(index);
            panel.id = `face-panel-${index}`;
            panel.querySelectorAll("[name], [id], [for]").forEach((element) => {
                ["name", "id", "for"].forEach((attribute) => {
                    const value = element.getAttribute(attribute);
                    if (!value) {
                        return;
                    }
                    const updated = value
                        .replace(/views-\d+-/g, `views-${index}-`)
                        .replace(/zone-\d+-/g, `zone-${index}-`)
                        .replace(/face-panel-\d+/g, `face-panel-${index}`);
                    if (updated !== value) {
                        element.setAttribute(attribute, updated);
                    }
                });
            });
            const number = panel.querySelector("[data-face-number]");
            if (number) {
                number.textContent = String(index + 1);
            }
        });
        totalFormsInput.value = String(allPanels.length);
        updateTabLabels();
    }


    function moveFace(index, direction) {
        const allPanels = panels();
        const target = index + direction;
        if (target < 0 || target >= allPanels.length) {
            return;
        }
        const panel = allPanels[index];
        if (direction < 0) {
            allPanels[target].before(panel);
        } else {
            allPanels[target].after(panel);
        }
        reindexFaces();
        rebuildTabs();
        setActiveFace(target);
    }

    function removeFace(index) {
        const allPanels = panels();
        if (allPanels.length <= 1) {
            return;
        }
        const panel = allPanels[index];
        revokePreview(panel);
        panel.remove();
        reindexFaces();
        rebuildTabs();
        setActiveFace(Math.min(index, allPanels.length - 2));
        updateAddState();
    }

    function addFace() {
        const allPanels = panels();
        if (allPanels.length >= maxFaces) {
            return;
        }
        const index = allPanels.length;
        const html = faceTemplate.innerHTML.replace(/__prefix__/g, String(index));
        const holder = document.createElement("div");
        holder.innerHTML = html.trim();
        const panel = holder.firstElementChild;
        if (!panel) {
            return;
        }

        facePanelsContainer.querySelector("[data-empty-faces]")?.remove();
        facePanelsContainer.append(panel);

        const fields = faceFields(panel);
        const name = defaultFaceName(index);
        if (fields.name && !fields.name.value) {
            fields.name.value = name;
        }
        if (fields.zoneName && !fields.zoneName.value) {
            fields.zoneName.value = `${name} artwork`;
        }
        if (fields.fullFace) {
            fields.fullFace.checked = false;
        }
        writeRatios(panel, DEFAULT_RATIOS);
        reindexFaces();
        initFace(panel);
        rebuildTabs();
        setActiveFace(index);
        updateAddState();
        fields.name?.focus();
    }


    function pointInStage(stage, event) {
        const bounds = stage.getBoundingClientRect();
        return {
            x: clamp(
                (event.clientX - bounds.left) / Math.max(bounds.width, 1),
                0,
                1
            ),
            y: clamp(
                (event.clientY - bounds.top) / Math.max(bounds.height, 1),
                0,
                1
            ),
        };
    }

    function beginPointerSession(panel, event, mode, onMove, onEnd) {
        if (event.button !== undefined && event.button !== 0) {
            return;
        }
        const fields = faceFields(panel);
        const stage = fields.stage;
        if (!stage) {
            return;
        }
        event.preventDefault();
        stage.classList.add(mode);

        const pointerId = event.pointerId;
        const move = (moveEvent) => {
            if (moveEvent.pointerId !== pointerId) {
                return;
            }
            moveEvent.preventDefault();
            onMove(moveEvent);
        };
        const end = (endEvent) => {
            if (endEvent.pointerId !== pointerId) {
                return;
            }
            document.removeEventListener("pointermove", move);
            document.removeEventListener("pointerup", end);
            document.removeEventListener("pointercancel", end);
            stage.classList.remove(mode);
            if (onEnd) {
                onEnd();
            }
            syncArea(panel);
        };

        document.addEventListener("pointermove", move, { passive: false });
        document.addEventListener("pointerup", end);
        document.addEventListener("pointercancel", end);
    }

    function bindAreaInteractions(panel) {
        const fields = faceFields(panel);
        const stage = fields.stage;
        const box = fields.areaBox;
        if (!stage || !box) {
            return;
        }

        stage.addEventListener("pointerdown", (event) => {
            if (!stage.classList.contains("is-editable")) {
                return;
            }
            if (fields.fullFace?.checked) {
                return;
            }
            panel.dataset.hintDismissed = "true";
            if (fields.hint) {
                fields.hint.hidden = true;
            }
            if (event.target.closest("[data-area-box]")) {
                return;
            }
            const start = pointInStage(stage, event);
            writeRatios(panel, {
                x: start.x,
                y: start.y,
                width: MIN_RATIO,
                height: MIN_RATIO,
            });
            syncArea(panel);

            beginPointerSession(panel, event, "is-drawing", (moveEvent) => {
                const current = pointInStage(stage, moveEvent);
                const left = Math.min(start.x, current.x);
                const top = Math.min(start.y, current.y);
                const width = Math.max(
                    Math.abs(current.x - start.x),
                    MIN_RATIO
                );
                const height = Math.max(
                    Math.abs(current.y - start.y),
                    MIN_RATIO
                );
                writeRatios(panel, {
                    x: left,
                    y: top,
                    width: Math.min(width, 1 - left),
                    height: Math.min(height, 1 - top),
                });
                syncArea(panel);
            });
        });

        box.addEventListener("pointerdown", (event) => {
            if (fields.fullFace?.checked) {
                return;
            }
            if (fields.hint) {
                fields.hint.hidden = true;
            }
            if (event.target.closest("[data-handle]")) {
                return;
            }
            const startPoint = pointInStage(stage, event);
            const startRatios = readRatios(panel);
            beginPointerSession(panel, event, "is-moving", (moveEvent) => {
                const current = pointInStage(stage, moveEvent);
                writeRatios(panel, {
                    x: clamp(
                        startRatios.x + current.x - startPoint.x,
                        0,
                        1 - startRatios.width
                    ),
                    y: clamp(
                        startRatios.y + current.y - startPoint.y,
                        0,
                        1 - startRatios.height
                    ),
                    width: startRatios.width,
                    height: startRatios.height,
                });
                syncArea(panel);
            });
        });


        panel.querySelectorAll("[data-handle]").forEach((handle) => {
            handle.tabIndex = -1;
            handle.addEventListener("pointerdown", (event) => {
                if (fields.fullFace?.checked) {
                    return;
                }
                const direction = handle.dataset.handle || "";
                const startPoint = pointInStage(stage, event);
                const startRatios = readRatios(panel);

                beginPointerSession(panel, event, "is-resizing", (moveEvent) => {
                    const current = pointInStage(stage, moveEvent);
                    const next = { ...startRatios };

                    if (direction.includes("e")) {
                        next.width = clamp(
                            current.x - startRatios.x,
                            MIN_RATIO,
                            1 - startRatios.x
                        );
                    }
                    if (direction.includes("w")) {
                        const right = startRatios.x + startRatios.width;
                        next.x = clamp(current.x, 0, right - MIN_RATIO);
                        next.width = right - next.x;
                    }
                    if (direction.includes("s")) {
                        next.height = clamp(
                            current.y - startRatios.y,
                            MIN_RATIO,
                            1 - startRatios.y
                        );
                    }
                    if (direction.includes("n")) {
                        const bottom = startRatios.y + startRatios.height;
                        next.y = clamp(current.y, 0, bottom - MIN_RATIO);
                        next.height = bottom - next.y;
                    }

                    writeRatios(panel, next);
                    syncArea(panel);
                });
            });
        });

        box.addEventListener("keydown", (event) => {
            if (fields.fullFace?.checked) {
                return;
            }
            const keys = ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"];
            if (!keys.includes(event.key)) {
                return;
            }
            event.preventDefault();
            const ratios = readRatios(panel);
            const step = event.shiftKey ? 0.01 : 0.02;

            if (event.shiftKey) {
                if (event.key === "ArrowLeft") {
                    ratios.width = clamp(
                        ratios.width - step,
                        MIN_RATIO,
                        1 - ratios.x
                    );
                } else if (event.key === "ArrowRight") {
                    ratios.width = clamp(
                        ratios.width + step,
                        MIN_RATIO,
                        1 - ratios.x
                    );
                } else if (event.key === "ArrowUp") {
                    ratios.height = clamp(
                        ratios.height - step,
                        MIN_RATIO,
                        1 - ratios.y
                    );
                } else if (event.key === "ArrowDown") {
                    ratios.height = clamp(
                        ratios.height + step,
                        MIN_RATIO,
                        1 - ratios.y
                    );
                }
            } else if (event.key === "ArrowLeft") {
                ratios.x = clamp(ratios.x - step, 0, 1 - ratios.width);
            } else if (event.key === "ArrowRight") {
                ratios.x = clamp(ratios.x + step, 0, 1 - ratios.width);
            } else if (event.key === "ArrowUp") {
                ratios.y = clamp(ratios.y - step, 0, 1 - ratios.height);
            } else if (event.key === "ArrowDown") {
                ratios.y = clamp(ratios.y + step, 0, 1 - ratios.height);
            }

            writeRatios(panel, ratios);
            syncArea(panel);
        });
    }


    function initFace(panel) {
        const fields = faceFields(panel);
        const state = stateFor(panel);

        if (!panel.dataset.wizardBound) {
            bindAreaInteractions(panel);

            fields.file?.addEventListener("change", () => loadPreview(panel));

            fields.name?.addEventListener("input", () => {
                const name = (fields.name.value || "").trim();
                const previous = panel.dataset.lastFaceName || "";
                const previousAuto = previous ? `${previous} artwork` : "";
                const currentZoneName = (fields.zoneName?.value || "").trim();
                if (
                    fields.zoneName &&
                    (!currentZoneName || currentZoneName === previousAuto)
                ) {
                    fields.zoneName.value = `${
                        name || defaultFaceName(panels().indexOf(panel))
                    } artwork`;
                }
                panel.dataset.lastFaceName = name;
                updateTabLabels();
            });

            fields.fullFace?.addEventListener("change", () => {
                if (fields.fullFace.checked) {
                    state.lastCustom = readRatios(panel);
                    writeRatios(panel, { x: 0, y: 0, width: 1, height: 1 });
                } else {
                    writeRatios(panel, state.lastCustom || DEFAULT_RATIOS);
                }
                syncArea(panel);
            });

            panel.querySelectorAll("[data-area-input]").forEach((input) => {
                input.addEventListener("input", () => {
                    if (fields.fullFace?.checked) {
                        return;
                    }
                    const value = parseFloat(input.value);
                    if (!Number.isFinite(value)) {
                        return;
                    }
                    const key = input.dataset.areaInput;
                    const percent = clamp(value, 0, 100) / 100;
                    const ratios = readRatios(panel);
                    if (key === "x") {
                        ratios.x = clamp(percent, 0, 1 - ratios.width);
                    } else if (key === "y") {
                        ratios.y = clamp(percent, 0, 1 - ratios.height);
                    } else if (key === "width") {
                        ratios.width = clamp(
                            percent,
                            MIN_RATIO,
                            1 - ratios.x
                        );
                    } else if (key === "height") {
                        ratios.height = clamp(
                            percent,
                            MIN_RATIO,
                            1 - ratios.y
                        );
                    }
                    writeRatios(panel, ratios);
                    syncArea(panel);
                    updateTabLabels();
                });
                input.addEventListener("blur", () => syncArea(panel));
            });

            panel.querySelector("[data-area-reset]")?.addEventListener(
                "click",
                () => {
                    if (fields.fullFace) {
                        fields.fullFace.checked = false;
                    }
                    state.lastCustom = { ...DEFAULT_RATIOS };
                    writeRatios(panel, DEFAULT_RATIOS);
                    syncArea(panel);
                    fields.areaBox?.focus();
                }
            );

            panel.dataset.wizardBound = "1";
        }

        const initialRatios = readRatios(panel);
        if (
            fields.fullFace?.checked &&
            initialRatios.width > 0.999 &&
            initialRatios.height > 0.999
        ) {
            state.lastCustom = { ...DEFAULT_RATIOS };
        } else {
            state.lastCustom = initialRatios;
        }

        const name = (fields.name?.value || "").trim();
        if (fields.zoneName && !fields.zoneName.value.trim() && name) {
            fields.zoneName.value = `${name} artwork`;
        }
        panel.dataset.lastFaceName = name || panel.dataset.lastFaceName || "";
        syncArea(panel);
    }


    function namedField(name) {
        return Array.from(form.elements).find((field) => field.name === name) || null;
    }

    function validateStepOne() {
        const panel = stepPanels.find(
            (candidate) => Number(candidate.dataset.wizardStep) === 1
        );
        if (!panel) {
            return true;
        }
        const fields = Array.from(
            panel.querySelectorAll("input, select, textarea")
        );
        for (const field of fields) {
            if (field.disabled || field.type === "hidden") {
                continue;
            }
            if (!field.checkValidity()) {
                field.classList.add("is-invalid");
                field.focus();
                field.reportValidity();
                return false;
            }
            field.classList.remove("is-invalid");
        }
        return true;
    }

    function validateStepTwo() {
        const allPanels = panels();
        if (!allPanels.length) {
            showGlobalErrors(["Add at least one product side."]);
            return false;
        }

        for (let index = 0; index < allPanels.length; index += 1) {
            const panel = allPanels[index];
            const fields = faceFields(panel);
            const requiredFields = [fields.name, fields.file];
            const invalidRequired = requiredFields.find(
                (field) => field && !field.checkValidity()
            );

            if (invalidRequired) {
                setActiveFace(index);
                showStep(2, { focus: false });
                invalidRequired.classList.add("is-invalid");
                invalidRequired.focus();
                invalidRequired.reportValidity();
                return false;
            }

            const advancedFields = Array.from(
                panel.querySelectorAll(
                    'input:not([type="hidden"]):not([type="file"]):not([data-area-input]), select, textarea'
                )
            );
            const invalidAdvanced = advancedFields.find(
                (field) => !field.disabled && !field.checkValidity()
            );
            if (invalidAdvanced) {
                setActiveFace(index);
                showStep(2, { focus: false });
                panel.querySelector(".wizard-advanced")?.setAttribute("open", "");
                invalidAdvanced.classList.add("is-invalid");
                invalidAdvanced.focus();
                invalidAdvanced.reportValidity();
                return false;
            }

            if (!fields.fullFace?.checked) {
                const ratios = readRatios(panel);
                if (
                    ratios.width <= 0 ||
                    ratios.height <= 0 ||
                    ratios.x + ratios.width > 1.000001 ||
                    ratios.y + ratios.height > 1.000001
                ) {
                    setActiveFace(index);
                    showStep(2, { focus: false });
                    if (fields.areaError) {
                        fields.areaError.textContent =
                            "Draw a printable area that fits inside the mockup.";
                    }
                    fields.areaBox?.focus();
                    return false;
                }
            }
        }

        return true;
    }

    function validateStep(step) {
        if (step === 1) {
            return validateStepOne();
        }
        if (step === 2) {
            return validateStepTwo();
        }
        return true;
    }

    function goToStep(target) {
        if (target > currentStep) {
            for (let step = currentStep; step < target; step += 1) {
                if (!validateStep(step)) {
                    showStep(step);
                    return false;
                }
            }
        }
        showStep(target);
        if (target === 3) {
            updateReview();
        }
        return true;
    }


    function updateReview() {
        const title =
            namedField("product-title")?.value.trim() || "Untitled product";
        const description =
            namedField("product-description")?.value.trim() || "No description";
        const priceValue = parseFloat(
            namedField("product-base_price")?.value || ""
        );
        const stockValue = namedField("product-stock_quantity")?.value || "0";
        const visible = Boolean(namedField("product-is_active")?.checked);

        const setText = (selector, value) => {
            const node = form.querySelector(selector);
            if (node) {
                node.textContent = value;
            }
        };

        setText("[data-review-title]", title);
        setText("[data-review-description]", description);
        setText(
            "[data-review-price]",
            Number.isFinite(priceValue) ? `€ ${priceValue.toFixed(2)}` : "—"
        );
        setText("[data-review-stock]", `${stockValue} units`);
        setText(
            "[data-review-visibility]",
            visible ? "Visible in the catalogue" : "Hidden from the catalogue"
        );

        const container = form.querySelector("[data-review-faces]");
        const countNode = form.querySelector("[data-review-face-count]");
        if (!container) {
            return;
        }
        container.textContent = "";

        const allPanels = panels();
        if (countNode) {
            countNode.textContent = `${allPanels.length} ${
                allPanels.length === 1 ? "side" : "sides"
            }`;
        }

        allPanels.forEach((panel, index) => {
            const fields = faceFields(panel);
            const name =
                (fields.name?.value || "").trim() || defaultFaceName(index);
            const zoneName =
                (fields.zoneName?.value || "").trim() || `${name} artwork`;
            const fullFace = Boolean(fields.fullFace?.checked);
            const ratios = fullFace
                ? { x: 0, y: 0, width: 1, height: 1 }
                : readRatios(panel);

            const card = document.createElement("div");
            card.className = "wizard-review-face";

            const thumb = document.createElement("div");
            thumb.className = "wizard-review-thumb";
            const image = fields.image;
            if (image && !image.hidden && image.getAttribute("src")) {
                const preview = document.createElement("img");
                preview.src = image.getAttribute("src");
                preview.alt = `${name} mockup preview`;
                thumb.append(preview);
            } else {
                const icon = document.createElement("i");
                icon.className = "bi bi-image";
                icon.setAttribute("aria-hidden", "true");
                thumb.append(icon);
            }

            const copy = document.createElement("div");
            copy.className = "wizard-review-face-copy";
            const strong = document.createElement("strong");
            strong.textContent = `${index + 1}. ${name}`;
            const zone = document.createElement("small");
            zone.textContent = zoneName;
            const area = document.createElement("span");
            area.className = "wizard-review-area";
            area.textContent = fullFace
                ? "Entire face"
                : `${formatPercent(ratios.width)}% × ${formatPercent(
                      ratios.height
                  )}% area`;
            copy.append(strong, zone, area);
            card.append(thumb, copy);
            container.append(card);
        });
    }


    function showGlobalErrors(messages) {
        if (!globalError) {
            return;
        }
        const cleanMessages = (messages || []).filter(Boolean);
        globalError.textContent = "";
        if (!cleanMessages.length) {
            globalError.classList.add("d-none");
            return;
        }
        const list = document.createElement("ul");
        list.className = "mb-0 ps-3";
        cleanMessages.forEach((message) => {
            const item = document.createElement("li");
            item.textContent = message;
            list.append(item);
        });
        globalError.append(list);
        globalError.classList.remove("d-none");
    }

    function clearServerErrors() {
        form.querySelectorAll(".wizard-server-error").forEach((node) => node.remove());
        form.querySelectorAll(".is-invalid").forEach((field) => {
            field.classList.remove("is-invalid");
            field.removeAttribute("aria-invalid");
        });
        form.querySelectorAll("[data-area-error]").forEach((node) => {
            node.textContent = "";
        });
        form.querySelectorAll("[data-area-box]").forEach((box) => {
            box.classList.remove("has-error");
        });
        showGlobalErrors([]);
    }

    function addFieldError(field, message) {
        field.classList.add("is-invalid");
        field.setAttribute("aria-invalid", "true");
        const feedback = document.createElement("div");
        feedback.className = "invalid-feedback d-block wizard-server-error";
        feedback.textContent = message;
        const upload = field.closest(".wizard-upload");
        if (upload) {
            upload.append(feedback);
        } else {
            field.insertAdjacentElement("afterend", feedback);
        }
    }

    function addAreaError(panel, message) {
        if (!panel) {
            return;
        }
        const fields = faceFields(panel);
        if (fields.areaError) {
            const existing = fields.areaError.textContent.trim();
            fields.areaError.textContent = existing
                ? `${existing} ${message}`
                : message;
        }
        fields.areaBox?.classList.add("has-error");
    }

    function applyServerErrors(data) {
        clearServerErrors();

        if (Number.isInteger(data.face_index)) {
            setActiveFace(data.face_index);
        }
        const step = Number(data.step);
        if (Number.isFinite(step)) {
            showStep(clamp(step, 1, 3), { focus: false });
            const top = form.getBoundingClientRect().top + window.scrollY - 96;
            window.scrollTo({ top: Math.max(top, 0), behavior: "auto" });
        }

        const general = [];
        (data.non_field_errors || []).forEach((message) => general.push(message));

        Object.entries(data.errors || {}).forEach(([name, messages]) => {
            const field = namedField(name);
            (messages || []).forEach((message) => {
                if (!field) {
                    general.push(`${name}: ${message}`);
                    return;
                }
                const panel = field.closest("[data-face-panel]");
                const isAreaField =
                    field.type === "hidden" ||
                    name.endsWith("_ratio") ||
                    name.endsWith("-full_face");
                if (panel && isAreaField) {
                    addAreaError(panel, message);
                } else {
                    field.closest(".wizard-advanced")?.setAttribute("open", "");
                    addFieldError(field, message);
                }
            });
        });

        if (data.message) {
            general.unshift(data.message);
        }
        showGlobalErrors(general);

        window.requestAnimationFrame(() => {
            const firstInvalid = form.querySelector(".is-invalid:not([type='hidden'])");
            if (firstInvalid) {
                firstInvalid.focus();
                return;
            }
            const activePanel = panelAt(activeFace);
            const areaError = activePanel?.querySelector("[data-area-error]");
            if (areaError?.textContent.trim()) {
                faceFields(activePanel).areaBox?.focus();
                return;
            }
            globalError?.focus();
        });
    }


    function setSubmitBusy(busy) {
        if (submitButton) {
            submitButton.disabled = busy;
        }
        submitSpinner?.classList.toggle("d-none", !busy);
        if (submitLabel) {
            submitLabel.textContent = busy ? "Creating product…" : "Create product";
        }
    }

    async function handleSubmit(event) {
        if (!window.fetch || typeof window.FormData === "undefined") {
            return;
        }
        event.preventDefault();
        if (submitBusy) {
            return;
        }
        if (!validateStepOne()) {
            showStep(1);
            return;
        }
        if (!validateStepTwo()) {
            return;
        }
        showStep(3);
        updateReview();

        submitBusy = true;
        setSubmitBusy(true);

        try {
            const response = await fetch(form.action || window.location.href, {
                method: "POST",
                body: new FormData(form),
                credentials: "same-origin",
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                    Accept: "application/json",
                },
            });
            const data = await response.json().catch(() => null);

            if (response.ok && data?.ok && data.redirect_url) {
                window.location.assign(data.redirect_url);
                return;
            }

            submitBusy = false;
            setSubmitBusy(false);
            if (data) {
                applyServerErrors(data);
            } else {
                showGlobalErrors([
                    "The server returned an unexpected response. Please try again.",
                ]);
            }
        } catch (error) {
            submitBusy = false;
            setSubmitBusy(false);
            showGlobalErrors([
                "The product could not be created because the connection failed. Please try again.",
            ]);
        }
    }

    stepIndicators.forEach((indicator) => {
        const button = indicator.querySelector("button");
        button?.addEventListener("click", () => {
            const target = Number(indicator.dataset.stepIndicator);
            if (target === currentStep) {
                return;
            }
            if (target > currentStep) {
                goToStep(target);
            } else {
                showStep(target);
            }
        });
    });

    form.querySelectorAll("[data-wizard-next]").forEach((button) => {
        button.addEventListener("click", () => {
            goToStep(Number(button.dataset.wizardNext));
        });
    });

    form.querySelectorAll("[data-wizard-back]").forEach((button) => {
        button.addEventListener("click", () => {
            showStep(Number(button.dataset.wizardBack));
        });
    });

    tabsNode.addEventListener("click", (event) => {
        const tab = event.target.closest("[data-face-tab]");
        if (tab) {
            setActiveFace(Number(tab.dataset.faceTab));
            return;
        }
        const action = event.target.closest("[data-face-action]");
        if (!action) {
            return;
        }
        const item = action.closest(".wizard-face-tab-item");
        const index = Number(
            item?.querySelector("[data-face-tab]")?.dataset.faceTab
        );
        if (!Number.isFinite(index)) {
            return;
        }
        if (action.dataset.faceAction === "up") {
            moveFace(index, -1);
        } else if (action.dataset.faceAction === "down") {
            moveFace(index, 1);
        } else if (action.dataset.faceAction === "remove") {
            removeFace(index);
        }
    });

    tabsNode.addEventListener("keydown", (event) => {
        const tab = event.target.closest("[data-face-tab]");
        if (!tab) {
            return;
        }
        const allTabs = Array.from(
            tabsNode.querySelectorAll("[data-face-tab]")
        );
        const index = allTabs.indexOf(tab);
        if (index === -1) {
            return;
        }
        let target = null;
        if (event.key === "ArrowLeft") {
            target = (index - 1 + allTabs.length) % allTabs.length;
        } else if (event.key === "ArrowRight") {
            target = (index + 1) % allTabs.length;
        } else if (event.key === "Home") {
            target = 0;
        } else if (event.key === "End") {
            target = allTabs.length - 1;
        }
        if (target === null) {
            return;
        }
        event.preventDefault();
        setActiveFace(target);
        tabsNode.querySelector(`[data-face-tab="${target}"]`)?.focus();
    });

    addFaceButton?.addEventListener("click", addFace);
    form.addEventListener("submit", handleSubmit);
    window.addEventListener("resize", scheduleStageFit);
    window.visualViewport?.addEventListener("resize", scheduleStageFit);
    window.addEventListener("pagehide", (event) => {
        if (!event.persisted) {
            panels().forEach(revokePreview);
        }
    });

    reindexFaces();
    panels().forEach(initFace);
    panels().forEach(fitStage);
    rebuildTabs();
    setActiveFace(activeFace);
    updateAddState();
    updateTabLabels();
    showStep(currentStep, { focus: false });
    if (currentStep === 3) {
        updateReview();
    }
})();

