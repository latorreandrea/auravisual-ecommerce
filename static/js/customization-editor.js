(() => {
    "use strict";

    const dataNode = document.getElementById("customization-editor-data");
    const form = document.getElementById("customization-form");
    if (!dataNode || !form) {
        return;
    }

    const data = JSON.parse(dataNode.textContent);
    const stage = document.getElementById("editor-stage");
    const mockup = document.getElementById("editor-mockup");
    const zonesLayer = document.getElementById("editor-zones");
    const tabs = document.getElementById("editor-view-tabs");
    const fileInputs = document.getElementById("editor-file-inputs");
    const configurationInput = document.getElementById("configuration-input");
    const uploadButton = document.getElementById("editor-upload-button");
    const removeButton = document.getElementById("editor-remove-image");
    const scaleInput = document.getElementById("editor-scale");
    const scaleValue = document.getElementById("editor-scale-value");
    const rotationInput = document.getElementById("editor-rotation");
    const rotationValue = document.getElementById("editor-rotation-value");
    const zoneName = document.getElementById("editor-zone-name");
    const controls = document.getElementById("editor-controls");
    const errorBox = document.getElementById("editor-error");
    const saveButton = document.getElementById("editor-save");

    const canReattachFiles = (() => {
        try {
            const probe = document.createElement("input");
            probe.type = "file";
            probe.files = new DataTransfer().files;
            return true;
        } catch (error) {
            return false;
        }
    })();

    const state = {
        views: data.views.map((view) => ({
            ...view,
            zones: view.zones.map((zone) => ({
                ...zone,
                file: null,
                previewUrl: "",
                assetPath: "",
                assetUrl: "",
                originalName: "",
                naturalWidth: 0,
                naturalHeight: 0,
                fit: null,
                transform: null,
            })),
        })),
        activeViewId: null,
        activeZoneId: null,
        canvasWidth: 0,
        canvasHeight: 0,
    };

    Object.entries(data.existing || {}).forEach(([viewId, zones]) => {
        const view = state.views.find((candidate) => String(candidate.id) === String(viewId));
        if (!view) {
            return;
        }
        Object.entries(zones).forEach(([zoneId, stored]) => {
            const zone = view.zones.find((candidate) => String(candidate.id) === String(zoneId));
            if (!zone) {
                return;
            }
            zone.assetPath = stored.asset_path || "";
            zone.assetUrl = stored.asset_url || "";
            zone.originalName = stored.original_name || "";
            zone.naturalWidth = stored.natural_width || 0;
            zone.naturalHeight = stored.natural_height || 0;
            zone.transform = stored.transform || null;
        });
    });

    function formatBytes(bytes) {
        if (!bytes) {
            return "0 MB";
        }
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    }

    function showError(message) {
        errorBox.textContent = message;
        errorBox.classList.remove("d-none");
    }

    function clearError() {
        errorBox.textContent = "";
        errorBox.classList.add("d-none");
    }

    function currentView() {
        return state.views.find((view) => view.id === state.activeViewId) || state.views[0];
    }

    function currentZone() {
        const view = currentView();
        if (!view) {
            return null;
        }
        return view.zones.find((zone) => zone.id === state.activeZoneId) || null;
    }

    function fitDimensions(naturalWidth, naturalHeight, zone) {
        if (!naturalWidth || !naturalHeight) {
            return { width: zone.width, height: zone.height };
        }
        const ratio = Math.min(zone.width / naturalWidth, zone.height / naturalHeight, 1);
        return {
            width: Math.max(1, naturalWidth * ratio),
            height: Math.max(1, naturalHeight * ratio),
        };
    }

    function syncStageRatio() {
        if (!stage || !state.canvasWidth || !state.canvasHeight) {
            return;
        }
        // Match the mockup to the editable canvas aspect ratio. The server
        // renderer uses the same width/height, so percentage based zone
        // coordinates line up in the editor and in the generated files.
        stage.style.aspectRatio = `${state.canvasWidth} / ${state.canvasHeight}`;
    }

    function clamp(value, minimum, maximum) {
        return Math.min(Math.max(value, minimum), maximum);
    }

    function defaultRotation(zone) {
        if (!zone.allow_rotation) {
            return 0;
        }
        return clamp(finiteNumber(zone.rotation, 0), -180, 180);
    }

    function finiteNumber(value, fallback) {
        if (typeof value === "number") {
            return Number.isFinite(value) ? value : fallback;
        }
        if (typeof value === "string" && value.trim() !== "") {
            const parsed = Number(value);
            return Number.isFinite(parsed) ? parsed : fallback;
        }
        return fallback;
    }

    function normalizeTransform(zone, transform) {
        const width = clamp(finiteNumber(transform.width, zone.width), 1, zone.width);
        let height = clamp(finiteNumber(transform.height, zone.height), 1, zone.height);

        if (zone.aspect_ratio_locked || !zone.allow_scaling) {
            const base = zone.fit || fitDimensions(zone.naturalWidth, zone.naturalHeight, zone);
            const ratio = base.width / base.height;
            height = width / ratio;
            if (height > zone.height) {
                height = zone.height;
                return normalizeTransform(zone, { ...transform, width: height * ratio, height });
            }
        }

        return {
            x: clamp(finiteNumber(transform.x, zone.x), zone.x, zone.x + zone.width - width),
            y: clamp(finiteNumber(transform.y, zone.y), zone.y, zone.y + zone.height - height),
            width,
            height,
            rotation: zone.allow_rotation
                ? clamp(finiteNumber(transform.rotation, 0), -180, 180)
                : 0,
        };
    }

    function ensureTransform(zone) {
        if (!zone.fit && zone.naturalWidth && zone.naturalHeight) {
            zone.fit = fitDimensions(zone.naturalWidth, zone.naturalHeight, zone);
        }
        if (!zone.transform) {
            const fit = zone.fit || { width: zone.width, height: zone.height };
            zone.transform = {
                x: zone.x + (zone.width - fit.width) / 2,
                y: zone.y + (zone.height - fit.height) / 2,
                width: fit.width,
                height: fit.height,
                rotation: defaultRotation(zone),
            };
        }
        zone.transform = normalizeTransform(zone, zone.transform);
        return zone.transform;
    }

    function percent(value, total) {
        return `${(value / total) * 100}%`;
    }

    function applyTransformToImage(zone) {
        const image = zonesLayer.querySelector(`[data-zone-image="${zone.id}"]`);
        if (!image) {
            return;
        }
        const transform = ensureTransform(zone);
        image.style.left = percent(transform.x - zone.x, zone.width);
        image.style.top = percent(transform.y - zone.y, zone.height);
        image.style.width = percent(transform.width, zone.width);
        image.style.height = percent(transform.height, zone.height);
        image.style.transform = `rotate(${transform.rotation}deg)`;
    }

    function attachDrag(image, zone) {
        let start = null;
        let moved = false;

        image.addEventListener("pointerdown", (event) => {
            if (event.button !== undefined && event.button !== 0) {
                return;
            }
            event.preventDefault();
            ensureTransform(zone);
            start = {
                x: event.clientX,
                y: event.clientY,
                transform: { ...zone.transform },
            };
            moved = false;
            state.activeZoneId = zone.id;
            zonesLayer.querySelectorAll(".editor-zone-clip").forEach((clip) => {
                clip.classList.toggle("is-selected", clip.contains(image));
            });
            updateSidebar();

            image.setPointerCapture(event.pointerId);
            image.dataset.dragging = "0";
            image.addEventListener("pointermove", onMove);
            image.addEventListener("pointerup", onUp);
            image.addEventListener("pointercancel", onUp);
        });

        function onMove(event) {
            if (!start) {
                return;
            }
            const view = currentView();
            const rect = stage.getBoundingClientRect();
            if (!view || !rect.width || !rect.height) {
                return;
            }
            const factorX = view.canvas_width / rect.width;
            const factorY = view.canvas_height / rect.height;
            const deltaX = (event.clientX - start.x) * factorX;
            const deltaY = (event.clientY - start.y) * factorY;
            if (Math.abs(deltaX) + Math.abs(deltaY) > 2) {
                moved = true;
            }
            zone.transform = normalizeTransform(zone, {
                ...start.transform,
                x: start.transform.x + deltaX,
                y: start.transform.y + deltaY,
            });
            applyTransformToImage(zone);
        }

        function onUp(event) {
            const target = event.currentTarget;
            target.releasePointerCapture?.(event.pointerId);
            target.removeEventListener("pointermove", onMove);
            target.removeEventListener("pointerup", onUp);
            target.removeEventListener("pointercancel", onUp);
            if (moved) {
                target.dataset.dragging = "1";
                window.setTimeout(() => {
                    target.dataset.dragging = "0";
                }, 0);
            }
            start = null;
            updateSidebar();
        }
    }

    function selectZone(zoneId, openPicker = false) {
        state.activeZoneId = zoneId;
        renderStage();
        updateSidebar();
        if (openPicker) {
            const input = fileInputs.querySelector(`input[data-zone-input="${zoneId}"]`);
            if (input) {
                if (canReattachFiles) {
                    input.value = "";
                }
                input.click();
            }
        }
    }

    function renderTabs() {
        tabs.innerHTML = "";
        state.views.forEach((view) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "editor-view-tab";
            button.textContent = view.name;
            button.setAttribute("role", "tab");
            button.setAttribute("aria-selected", view.id === state.activeViewId ? "true" : "false");
            button.classList.toggle("is-active", view.id === state.activeViewId);
            button.addEventListener("click", () => {
                state.activeViewId = view.id;
                state.activeZoneId = null;
                renderStage();
                updateSidebar();
            });
            tabs.appendChild(button);
        });
    }

    function renderStage() {
        const view = currentView();
        if (!view) {
            return;
        }
        state.activeViewId = view.id;
        state.canvasWidth = Number(view.canvas_width) || 0;
        state.canvasHeight = Number(view.canvas_height) || 0;
        syncStageRatio();

        mockup.src = view.mockup_url;
        mockup.alt = `${data.product.title} - ${view.name}`;

        let overlay = document.getElementById("editor-overlay");
        if (!overlay) {
            overlay = document.createElement("img");
            overlay.id = "editor-overlay";
            overlay.className = "editor-overlay";
            overlay.alt = "";
            mockup.insertAdjacentElement("afterend", overlay);
        }
        overlay.hidden = !view.overlay_url;
        overlay.src = view.overlay_url || "";

        zonesLayer.innerHTML = "";
        view.zones.forEach((zone) => {
            const clip = document.createElement("div");
            clip.className = "editor-zone-clip";
            clip.style.left = percent(zone.x, view.canvas_width);
            clip.style.top = percent(zone.y, view.canvas_height);
            clip.style.width = percent(zone.width, view.canvas_width);
            clip.style.height = percent(zone.height, view.canvas_height);
            clip.title = `${zone.name} - ${formatBytes(zone.max_upload_bytes)} max`;
            clip.classList.toggle("is-selected", zone.id === state.activeZoneId);

            const hasImage = Boolean(zone.previewUrl || zone.assetUrl);
            if (hasImage) {
                const transform = ensureTransform(zone);
                const image = document.createElement("img");
                image.className = "editor-zone-image";
                image.dataset.zoneImage = zone.id;
                image.src = zone.previewUrl || zone.assetUrl;
                image.alt = zone.originalName || `${zone.name} artwork`;
                image.draggable = false;
                image.style.left = percent(transform.x - zone.x, zone.width);
                image.style.top = percent(transform.y - zone.y, zone.height);
                image.style.width = percent(transform.width, zone.width);
                image.style.height = percent(transform.height, zone.height);
                image.style.transform = `rotate(${transform.rotation}deg)`;
                clip.appendChild(image);
                attachDrag(image, zone);
            } else {
                const hint = document.createElement("span");
                hint.className = "editor-zone-hint";
                hint.textContent = "+";
                hint.setAttribute("aria-hidden", "true");
                clip.appendChild(hint);
            }

            clip.addEventListener("click", (event) => {
                if (event.target.dataset && event.target.dataset.dragging === "1") {
                    return;
                }
                selectZone(zone.id, !hasImage);
            });
            zonesLayer.appendChild(clip);
        });

        renderTabs();
    }

    function updateSidebar() {
        const zone = currentZone();
        const view = currentView();
        if (!zone || !view) {
            zoneName.textContent = "Select an area on the product.";
            uploadButton.disabled = true;
            uploadButton.innerHTML = '<i class="bi bi-upload me-2"></i>Choose image';
            controls.classList.add("d-none");
            return;
        }

        const hasImage = Boolean(zone.previewUrl || zone.assetUrl);
        zoneName.textContent = `${zone.name} (${view.name})`;
        uploadButton.disabled = false;
        uploadButton.innerHTML = hasImage
            ? '<i class="bi bi-arrow-repeat me-2"></i>Replace image'
            : '<i class="bi bi-upload me-2"></i>Choose image';
        controls.classList.toggle("d-none", !hasImage);

        const scaleRow = document.getElementById("editor-scale-row");
        if (scaleRow) {
            scaleRow.classList.toggle("d-none", !zone.allow_scaling);
        }
        const rotationRow = document.getElementById("editor-rotation-row");
        if (rotationRow) {
            rotationRow.classList.toggle("d-none", !zone.allow_rotation);
        }

        if (hasImage) {
            const transform = ensureTransform(zone);
            const reference = zone.fit || fitDimensions(zone.naturalWidth, zone.naturalHeight, zone);
            const scalePercent = reference.width
                ? clamp(Math.round((transform.width / reference.width) * 100), 25, 100)
                : 100;
            scaleInput.value = String(scalePercent);
            scaleValue.textContent = `${scalePercent}%`;
            rotationInput.value = String(Math.round(transform.rotation));
            rotationValue.textContent = `${Math.round(transform.rotation)}\u00b0`;
        }
    }

    function zoneInput(zoneId) {
        return fileInputs.querySelector(`input[data-zone-input="${zoneId}"]`);
    }

    function syncZoneFiles() {
        let ok = true;
        state.views.forEach((view) => {
            view.zones.forEach((zone) => {
                if (!zone.file) {
                    return;
                }
                const input = zoneInput(zone.id);
                if (!input) {
                    ok = false;
                    return;
                }
                if (canReattachFiles) {
                    try {
                        const transfer = new DataTransfer();
                        transfer.items.add(zone.file);
                        input.files = transfer.files;
                    } catch (error) {
                        ok = false;
                    }
                }
                if (canReattachFiles) {
                    if (!input.files || !input.files.length) {
                        ok = false;
                    }
                } else if (!input.files || input.files[0] !== zone.file) {
                    ok = false;
                }
            });
        });
        return ok;
    }

    function onFileSelected(zone, input) {
        clearError();
        const file = input.files && input.files[0];
        if (!file) {
            return;
        }

        const allowedTypes = ["image/png", "image/jpeg", "image/webp"];
        const allowedExtensions = ["png", "jpg", "jpeg", "webp"];
        const extension = file.name.includes(".")
            ? file.name.split(".").pop().toLowerCase()
            : "";
        if (!allowedTypes.includes(file.type) && !allowedExtensions.includes(extension)) {
            showError("Please choose a PNG, JPEG or WebP image.");
            input.value = "";
            return;
        }
        if (file.size > zone.max_upload_bytes) {
            showError(
                `"${file.name}" is too large. The maximum for this area is ${formatBytes(zone.max_upload_bytes)}.`
            );
            input.value = "";
            return;
        }

        const objectUrl = URL.createObjectURL(file);
        const image = new Image();
        const requestId = (zone.uploadRequestId || 0) + 1;
        zone.uploadRequestId = requestId;
        image.onload = () => {
            if (zone.uploadRequestId !== requestId) {
                URL.revokeObjectURL(objectUrl);
                return;
            }
            if (image.naturalWidth * image.naturalHeight > data.max_image_pixels) {
                URL.revokeObjectURL(objectUrl);
                showError("The image has too many pixels. Please choose a smaller file.");
                input.value = "";
                return;
            }

            if (zone.previewUrl) {
                URL.revokeObjectURL(zone.previewUrl);
            }
            zone.file = file;
            zone.previewUrl = objectUrl;
            zone.assetPath = "";
            zone.assetUrl = "";
            zone.originalName = file.name;
            zone.naturalWidth = image.naturalWidth;
            zone.naturalHeight = image.naturalHeight;
            zone.fit = fitDimensions(image.naturalWidth, image.naturalHeight, zone);
            zone.transform = normalizeTransform(zone, {
                x: zone.x + (zone.width - zone.fit.width) / 2,
                y: zone.y + (zone.height - zone.fit.height) / 2,
                width: zone.fit.width,
                height: zone.fit.height,
                rotation: defaultRotation(zone),
            });
            // Keep the File on the zone state. The native input can be cleared
            // so the same path can be picked again, then populated from state
            // immediately before submission.
            if (canReattachFiles) {
                input.value = "";
            }

            state.activeZoneId = zone.id;
            renderStage();
            updateSidebar();
        };
        image.onerror = () => {
            URL.revokeObjectURL(objectUrl);
            if (zone.uploadRequestId !== requestId) {
                return;
            }
            showError("The selected file is not a readable image.");
            input.value = "";
        };
        image.src = objectUrl;
    }

    function removeImage() {
        const zone = currentZone();
        if (!zone) {
            return;
        }
        if (zone.previewUrl) {
            URL.revokeObjectURL(zone.previewUrl);
        }
        zone.file = null;
        zone.uploadRequestId = (zone.uploadRequestId || 0) + 1;
        zone.previewUrl = "";
        zone.assetPath = "";
        zone.assetUrl = "";
        zone.originalName = "";
        zone.naturalWidth = 0;
        zone.naturalHeight = 0;
        zone.fit = null;
        zone.transform = null;
        const input = zoneInput(zone.id);
        if (input) {
            input.value = "";
        }
        renderStage();
        updateSidebar();
        clearError();
    }

    uploadButton.addEventListener("click", () => {
        const zone = currentZone();
        if (!zone) {
            return;
        }
        const input = zoneInput(zone.id);
        if (input) {
            if (canReattachFiles) {
                input.value = "";
            }
            input.click();
        }
    });

    removeButton.addEventListener("click", removeImage);

    scaleInput.addEventListener("input", () => {
        const zone = currentZone();
        if (!zone || !zone.fit) {
            return;
        }
        const percentage = Number(scaleInput.value);
        const transform = ensureTransform(zone);
        const centerX = transform.x + transform.width / 2;
        const centerY = transform.y + transform.height / 2;
        const width = clamp(zone.fit.width * (percentage / 100), 1, zone.width);
        const height = clamp(zone.fit.height * (percentage / 100), 1, zone.height);
        zone.transform = normalizeTransform(zone, {
            ...transform,
            width,
            height,
            x: centerX - width / 2,
            y: centerY - height / 2,
        });
        applyTransformToImage(zone);
        scaleValue.textContent = `${percentage}%`;
    });

    rotationInput.addEventListener("input", () => {
        const zone = currentZone();
        if (!zone || !zone.allow_rotation) {
            return;
        }
        const rotation = Number(rotationInput.value);
        zone.transform = normalizeTransform(zone, {
            ...ensureTransform(zone),
            rotation,
        });
        applyTransformToImage(zone);
        rotationValue.textContent = `${rotation}\u00b0`;
    });

    form.addEventListener("submit", (event) => {
        const views = state.views
            .map((view) => ({
                product_view_id: view.id,
                zones: view.zones
                    .filter((zone) => zone.file || zone.assetPath)
                    .map((zone) => ({
                        zone_id: zone.id,
                        asset_path: zone.file ? "" : zone.assetPath,
                        original_name: zone.originalName,
                        transform: ensureTransform(zone),
                    })),
            }))
            .filter((view) => view.zones.length);

        if (!views.length) {
            event.preventDefault();
            showError("Add at least one image before saving your customization.");
            return;
        }

        if (!syncZoneFiles()) {
            event.preventDefault();
            showError("The selected image could not be attached. Please choose it again.");
            return;
        }

        configurationInput.value = JSON.stringify({ views });
        saveButton.disabled = true;
        saveButton.innerHTML =
            '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Saving...';
    });

    state.views.forEach((view) => {
        view.zones.forEach((zone) => {
            const input = document.createElement("input");
            input.type = "file";
            input.name = `asset_${zone.id}`;
            input.accept = "image/png,image/jpeg,image/webp";
            input.dataset.zoneInput = zone.id;
            input.addEventListener("change", () => onFileSelected(zone, input));
            fileInputs.appendChild(input);
        });
    });

    const initialView =
        state.views.find((view) => view.zones.some((zone) => zone.assetPath)) || state.views[0];
    state.activeViewId = initialView ? initialView.id : null;
    const initialZone =
        initialView && initialView.zones.find((zone) => zone.assetPath);
    state.activeZoneId = initialZone ? initialZone.id : null;

    renderStage();
    updateSidebar();
})();
