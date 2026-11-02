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
    const artworkLayer = document.getElementById("editor-artwork");
    const tabs = document.getElementById("editor-view-tabs");
    const fileInputs = document.getElementById("editor-file-inputs");
    const configurationInput = document.getElementById("configuration-input");
    const uploadButton = document.getElementById("editor-upload-button");
    const removeButton = document.getElementById("editor-remove-image");
    const scaleInput = document.getElementById("editor-scale");
    const scaleValue = document.getElementById("editor-scale-value");
    const rotationInput = document.getElementById("editor-rotation");
    const rotationValue = document.getElementById("editor-rotation-value");
    const rotationRow = document.getElementById("editor-rotation-row");
    const sideName = document.getElementById("editor-side-name");
    const controls = document.getElementById("editor-controls");
    const errorBox = document.getElementById("editor-error");
    const saveButton = document.getElementById("editor-save");

    const MAX_SCALE = 2;

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

    // One image per side: the state mirrors what the server will store.
    const state = {
        views: data.views.map((view) => ({
            ...view,
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
        activeViewId: null,
        canvasWidth: 0,
        canvasHeight: 0,
    };

    Object.entries(data.existing || {}).forEach(([viewId, stored]) => {
        const view = state.views.find((candidate) => String(candidate.id) === String(viewId));
        if (!view || !stored) {
            return;
        }
        view.assetPath = stored.asset_path || "";
        view.assetUrl = stored.asset_url || "";
        view.originalName = stored.original_name || "";
        view.naturalWidth = stored.natural_width || 0;
        view.naturalHeight = stored.natural_height || 0;
        view.transform = stored.transform || null;
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
        return (
            state.views.find((view) => view.id === state.activeViewId) ||
            state.views[0] ||
            null
        );
    }

    function hasImage(view) {
        return Boolean(view && (view.previewUrl || view.assetUrl));
    }

    function clamp(value, minimum, maximum) {
        return Math.min(Math.max(value, minimum), maximum);
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

    // The image never starts bigger than its printable area.
    function fitDimensions(view, naturalWidth, naturalHeight) {
        const box = view.print_area;
        if (!naturalWidth || !naturalHeight) {
            return { width: box.width, height: box.height };
        }
        const ratio = Math.min(box.width / naturalWidth, box.height / naturalHeight, 1);
        return {
            width: Math.max(1, naturalWidth * ratio),
            height: Math.max(1, naturalHeight * ratio),
        };
    }

    function defaultRotation(view) {
        if (!view.print_area.allow_rotation) {
            return 0;
        }
        return clamp(finiteNumber(view.print_area.rotation, 0), -180, 180);
    }

    function normalizeTransform(view, transform) {
        const box = view.print_area;
        const maxWidth = box.width * MAX_SCALE;
        const maxHeight = box.height * MAX_SCALE;

        let width = clamp(finiteNumber(transform.width, box.width), 1, maxWidth);
        let height = clamp(finiteNumber(transform.height, box.height), 1, maxHeight);

        if (!box.allow_scaling) {
            const fit = fitDimensions(view, view.naturalWidth, view.naturalHeight);
            width = fit.width;
            height = fit.height;
        } else if (box.aspect_ratio_locked) {
            const fit = fitDimensions(view, view.naturalWidth, view.naturalHeight);
            const ratio = fit.height ? fit.width / fit.height : 1;
            height = width / ratio;
            if (height > maxHeight) {
                height = maxHeight;
                width = height * ratio;
            }
        }

        // Keep the centre of the image inside the printable area.
        const desiredCenterX = finiteNumber(
            transform.x,
            box.x + (box.width - width) / 2
        ) + width / 2;
        const desiredCenterY = finiteNumber(
            transform.y,
            box.y + (box.height - height) / 2
        ) + height / 2;
        const centerX = clamp(desiredCenterX, box.x, box.x + box.width);
        const centerY = clamp(desiredCenterY, box.y, box.y + box.height);

        return {
            x: centerX - width / 2,
            y: centerY - height / 2,
            width,
            height,
            rotation: box.allow_rotation
                ? clamp(finiteNumber(transform.rotation, 0), -180, 180)
                : 0,
        };
    }

    function ensureTransform(view) {
        if (!view.transform) {
            const box = view.print_area;
            const fit = fitDimensions(view, view.naturalWidth, view.naturalHeight);
            view.fit = fit;
            view.transform = {
                x: box.x + (box.width - fit.width) / 2,
                y: box.y + (box.height - fit.height) / 2,
                width: fit.width,
                height: fit.height,
                rotation: defaultRotation(view),
            };
        }
        view.transform = normalizeTransform(view, view.transform);
        return view.transform;
    }

    function percent(value, total) {
        return `${(value / total) * 100}%`;
    }

    function applyTransformToImage(view) {
        const image = artworkLayer.querySelector("[data-artwork-image]");
        if (!image) {
            return;
        }
        const box = view.print_area;
        const transform = ensureTransform(view);
        image.style.left = percent(transform.x - box.x, box.width);
        image.style.top = percent(transform.y - box.y, box.height);
        image.style.width = percent(transform.width, box.width);
        image.style.height = percent(transform.height, box.height);
        image.style.transform = `rotate(${transform.rotation}deg)`;
    }

    function attachDrag(image, view) {
        let start = null;
        let moved = false;

        image.addEventListener("pointerdown", (event) => {
            if (event.button !== undefined && event.button !== 0) {
                return;
            }
            event.preventDefault();
            const transform = ensureTransform(view);
            start = { x: event.clientX, y: event.clientY, transform: { ...transform } };
            moved = false;

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
            const rect = stage.getBoundingClientRect();
            if (!rect.width || !rect.height) {
                return;
            }
            const factorX = view.canvas_width / rect.width;
            const factorY = view.canvas_height / rect.height;
            const deltaX = (event.clientX - start.x) * factorX;
            const deltaY = (event.clientY - start.y) * factorY;
            if (Math.abs(deltaX) + Math.abs(deltaY) > 2) {
                moved = true;
            }
            view.transform = normalizeTransform(view, {
                ...start.transform,
                x: start.transform.x + deltaX,
                y: start.transform.y + deltaY,
            });
            applyTransformToImage(view);
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
        }
    }

    function selectView(viewId, openPicker = false) {
        state.activeViewId = viewId;
        renderStage();
        updateSidebar();
        if (openPicker) {
            openPickerFor(viewId);
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
            button.setAttribute(
                "aria-selected",
                view.id === state.activeViewId ? "true" : "false"
            );
            button.classList.toggle("is-active", view.id === state.activeViewId);
            button.classList.toggle("has-image", hasImage(view));
            button.addEventListener("click", () => selectView(view.id));
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

        if (state.canvasWidth && state.canvasHeight) {
            // Same aspect ratio the server renderer uses, so percentage based
            // coordinates line up in the editor and in the generated files.
            stage.style.aspectRatio = `${state.canvasWidth} / ${state.canvasHeight}`;
        }

        mockup.src = view.mockup_url;
        mockup.alt = `${data.product.title} - ${view.name}`;

        artworkLayer.innerHTML = "";
        const box = view.print_area;
        const area = document.createElement("div");
        area.className = "editor-print-area";
        area.style.left = percent(box.x, view.canvas_width);
        area.style.top = percent(box.y, view.canvas_height);
        area.style.width = percent(box.width, view.canvas_width);
        area.style.height = percent(box.height, view.canvas_height);
        area.title = `${view.name} - printable area`;

        if (hasImage(view)) {
            const transform = ensureTransform(view);
            const image = document.createElement("img");
            image.className = "editor-artwork-image";
            image.dataset.artworkImage = "1";
            image.src = view.previewUrl || view.assetUrl;
            image.alt = view.originalName || `${view.name} artwork`;
            image.draggable = false;
            image.style.left = percent(transform.x - box.x, box.width);
            image.style.top = percent(transform.y - box.y, box.height);
            image.style.width = percent(transform.width, box.width);
            image.style.height = percent(transform.height, box.height);
            image.style.transform = `rotate(${transform.rotation}deg)`;
            area.appendChild(image);
            attachDrag(image, view);
        } else {
            const hint = document.createElement("span");
            hint.className = "editor-artwork-hint";
            hint.textContent = "+";
            hint.setAttribute("aria-hidden", "true");
            area.appendChild(hint);
        }

        area.addEventListener("click", (event) => {
            if (event.target.dataset && event.target.dataset.dragging === "1") {
                return;
            }
            selectView(view.id, !hasImage(view));
        });
        artworkLayer.appendChild(area);

        renderTabs();
    }

    function updateSidebar() {
        const view = currentView();
        if (!view) {
            sideName.textContent = "Select a side.";
            uploadButton.disabled = true;
            controls.classList.add("d-none");
            return;
        }

        const filled = hasImage(view);
        sideName.textContent = `${view.name} - printable area ${formatBytes(view.max_upload_bytes)} max`;
        uploadButton.disabled = false;
        uploadButton.innerHTML = filled
            ? '<i class="bi bi-arrow-repeat me-2"></i>Replace image'
            : '<i class="bi bi-upload me-2"></i>Choose image';
        controls.classList.toggle("d-none", !filled);
        rotationRow.classList.toggle("d-none", !view.print_area.allow_rotation);

        if (!filled) {
            return;
        }

        const transform = ensureTransform(view);
        const fit = view.fit || fitDimensions(view, view.naturalWidth, view.naturalHeight);
        const scalePercent = fit.width
            ? clamp(Math.round((transform.width / fit.width) * 100), 25, MAX_SCALE * 100)
            : 100;
        scaleInput.value = String(scalePercent);
        scaleValue.textContent = `${scalePercent}%`;
        rotationInput.value = String(Math.round(transform.rotation));
        rotationValue.textContent = `${Math.round(transform.rotation)}\u00b0`;
    }

    function viewInput(viewId) {
        return fileInputs.querySelector(`input[data-view-input="${viewId}"]`);
    }

    function openPickerFor(viewId) {
        const input = viewInput(viewId);
        if (!input) {
            return;
        }
        if (canReattachFiles) {
            input.value = "";
        }
        input.click();
    }

    function syncFiles() {
        let ok = true;
        state.views.forEach((view) => {
            if (!view.file) {
                return;
            }
            const input = viewInput(view.id);
            if (!input) {
                ok = false;
                return;
            }
            if (canReattachFiles) {
                try {
                    const transfer = new DataTransfer();
                    transfer.items.add(view.file);
                    input.files = transfer.files;
                } catch (error) {
                    ok = false;
                }
                if (!input.files || !input.files.length) {
                    ok = false;
                }
            } else if (!input.files || input.files[0] !== view.file) {
                ok = false;
            }
        });
        return ok;
    }

    function onFileSelected(view, input) {
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
        if (file.size > view.max_upload_bytes) {
            showError(
                `"${file.name}" is too large. The maximum for this side is ${formatBytes(
                    view.max_upload_bytes
                )}.`
            );
            input.value = "";
            return;
        }

        const objectUrl = URL.createObjectURL(file);
        const image = new Image();
        const requestId = (view.uploadRequestId || 0) + 1;
        view.uploadRequestId = requestId;
        image.onload = () => {
            if (view.uploadRequestId !== requestId) {
                URL.revokeObjectURL(objectUrl);
                return;
            }
            if (image.naturalWidth * image.naturalHeight > data.max_image_pixels) {
                URL.revokeObjectURL(objectUrl);
                showError("The image has too many pixels. Please choose a smaller file.");
                input.value = "";
                return;
            }

            if (view.previewUrl) {
                URL.revokeObjectURL(view.previewUrl);
            }
            const box = view.print_area;
            view.file = file;
            view.previewUrl = objectUrl;
            view.assetPath = "";
            view.assetUrl = "";
            view.originalName = file.name;
            view.naturalWidth = image.naturalWidth;
            view.naturalHeight = image.naturalHeight;
            view.fit = fitDimensions(view, image.naturalWidth, image.naturalHeight);
            view.transform = {
                x: box.x + (box.width - view.fit.width) / 2,
                y: box.y + (box.height - view.fit.height) / 2,
                width: view.fit.width,
                height: view.fit.height,
                rotation: defaultRotation(view),
            };
            // Keep the File on the view state. The native input can be cleared
            // so the same path can be picked again, then populated from state
            // immediately before submission.
            if (canReattachFiles) {
                input.value = "";
            }
            state.activeViewId = view.id;
            renderStage();
            updateSidebar();
        };
        image.onerror = () => {
            URL.revokeObjectURL(objectUrl);
            if (view.uploadRequestId !== requestId) {
                return;
            }
            showError("The selected file is not a readable image.");
            input.value = "";
        };
        image.src = objectUrl;
    }

    function removeImage() {
        const view = currentView();
        if (!view) {
            return;
        }
        if (view.previewUrl) {
            URL.revokeObjectURL(view.previewUrl);
        }
        view.file = null;
        view.uploadRequestId = (view.uploadRequestId || 0) + 1;
        view.previewUrl = "";
        view.assetPath = "";
        view.assetUrl = "";
        view.originalName = "";
        view.naturalWidth = 0;
        view.naturalHeight = 0;
        view.fit = null;
        view.transform = null;
        const input = viewInput(view.id);
        if (input) {
            input.value = "";
        }
        renderStage();
        updateSidebar();
        clearError();
    }

    uploadButton.addEventListener("click", () => {
        const view = currentView();
        if (view) {
            openPickerFor(view.id);
        }
    });

    removeButton.addEventListener("click", removeImage);

    scaleInput.addEventListener("input", () => {
        const view = currentView();
        if (!view || !hasImage(view)) {
            return;
        }
        const box = view.print_area;
        const percentage = Number(scaleInput.value);
        const fit = view.fit || fitDimensions(view, view.naturalWidth, view.naturalHeight);
        const transform = ensureTransform(view);
        const width = clamp(fit.width * (percentage / 100), 1, box.width * MAX_SCALE);
        const height = clamp(fit.height * (percentage / 100), 1, box.height * MAX_SCALE);
        view.transform = normalizeTransform(view, { ...transform, width, height });
        applyTransformToImage(view);
        scaleValue.textContent = `${percentage}%`;
    });

    rotationInput.addEventListener("input", () => {
        const view = currentView();
        if (!view || !hasImage(view) || !view.print_area.allow_rotation) {
            return;
        }
        const rotation = Number(rotationInput.value);
        view.transform = normalizeTransform(view, {
            ...ensureTransform(view),
            rotation,
        });
        applyTransformToImage(view);
        rotationValue.textContent = `${rotation}\u00b0`;
    });

    form.addEventListener("submit", (event) => {
        const views = state.views
            .filter((view) => view.file || view.assetPath)
            .map((view) => ({
                product_view_id: view.id,
                image: {
                    asset_path: view.file ? "" : view.assetPath,
                    original_name: view.originalName,
                    transform: ensureTransform(view),
                },
            }));

        if (!views.length) {
            event.preventDefault();
            showError("Add at least one image before saving your project.");
            return;
        }

        if (!syncFiles()) {
            event.preventDefault();
            showError("The selected image could not be attached. Please choose it again.");
            return;
        }

        configurationInput.value = JSON.stringify({ views });
        saveButton.disabled = true;
        saveButton.innerHTML =
            '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Saving...';
    });

    // One hidden file input per customizable side.
    state.views.forEach((view) => {
        const input = document.createElement("input");
        input.type = "file";
        input.name = `asset_${view.id}`;
        input.accept = "image/png,image/jpeg,image/webp";
        input.dataset.viewInput = view.id;
        input.addEventListener("change", () => onFileSelected(view, input));
        fileInputs.appendChild(input);
    });

    const initialView = state.views.find((view) => view.assetPath) || state.views[0];
    state.activeViewId = initialView ? initialView.id : null;

    renderStage();
    updateSidebar();
})();
