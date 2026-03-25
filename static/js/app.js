(() => {
    const doc = document.documentElement;
    const loadingOverlay = document.getElementById("loadingOverlay");
    const loadingMessage = document.getElementById("loadingMessage");
    const themeToggle = document.getElementById("themeToggle");
    const uploadInput = document.getElementById("uploadModalInput");
    const uploadPreview = document.getElementById("uploadPreview");
    const uploadPreviewImage = document.getElementById("uploadPreviewImage");
    const uploadPreviewName = document.getElementById("uploadPreviewName");
    const uploadPreviewMeta = document.getElementById("uploadPreviewMeta");
    const uploadEmptyNote = document.getElementById("uploadEmptyNote");
    const uploadDropzone = document.getElementById("uploadDropzone");
    const uploadForm = document.getElementById("uploadForm");
    const uploadModalElement = document.getElementById("uploadModal");
    const uploadSubmitButton = document.getElementById("uploadSubmitButton");
    const detailModal = document.getElementById("imageDetailModal");

    let previewObjectUrl = null;

    const setTheme = (theme) => {
        doc.setAttribute("data-bs-theme", theme);

        if (themeToggle) {
            const isDark = theme === "dark";
            themeToggle.textContent = isDark ? "Thème clair" : "Thème sombre";
            themeToggle.setAttribute("aria-pressed", String(isDark));
        }
    };

    const initTheme = () => {
        const storedTheme = window.localStorage.getItem("smartdam-theme");
        const preferredDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
        setTheme(storedTheme || (preferredDark ? "dark" : "light"));
    };

    const showLoadingOverlay = (message) => {
        if (!loadingOverlay) {
            return;
        }

        if (loadingMessage) {
            loadingMessage.textContent = message || "Chargement en cours...";
        }

        loadingOverlay.hidden = false;
    };

    const decorateSubmitButton = (button) => {
        if (!button) {
            return;
        }

        button.disabled = true;
        const spinner = button.querySelector(".spinner-border");
        if (spinner) {
            spinner.classList.remove("d-none");
        }
    };

    const bindLoadingForms = () => {
        document.querySelectorAll("[data-loading-form]").forEach((form) => {
            form.addEventListener("submit", (event) => {
                if (!form.checkValidity()) {
                    return;
                }

                const submitter = event.submitter;
                const message = form.dataset.loadingMessage || submitter?.dataset.loadingMessage || "Chargement en cours...";
                showLoadingOverlay(message);
                decorateSubmitButton(submitter);
            });
        });
    };

    const resetUploadPreview = () => {
        if (previewObjectUrl) {
            URL.revokeObjectURL(previewObjectUrl);
            previewObjectUrl = null;
        }

        if (uploadPreviewImage) {
            uploadPreviewImage.src = "";
        }
        if (uploadPreviewName) {
            uploadPreviewName.textContent = "Aucun fichier";
        }
        if (uploadPreviewMeta) {
            uploadPreviewMeta.textContent = "Sélectionnez un fichier pour voir son aperçu.";
        }
        if (uploadPreview) {
            uploadPreview.hidden = true;
        }
        if (uploadEmptyNote) {
            uploadEmptyNote.hidden = false;
        }
        if (uploadDropzone) {
            uploadDropzone.classList.remove("is-dragover");
        }
        if (uploadSubmitButton) {
            uploadSubmitButton.disabled = false;
            const spinner = uploadSubmitButton.querySelector(".spinner-border");
            if (spinner) {
                spinner.classList.add("d-none");
            }
        }
    };

    const formatFileSize = (bytes) => {
        if (!bytes) {
            return "0 Ko";
        }

        if (bytes >= 1024 * 1024) {
            return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
        }

        return `${Math.max(1, Math.round(bytes / 1024))} Ko`;
    };

    const updateUploadPreview = (file) => {
        if (!file || !uploadPreview || !uploadPreviewImage || !uploadPreviewName || !uploadPreviewMeta) {
            return;
        }

        if (previewObjectUrl) {
            URL.revokeObjectURL(previewObjectUrl);
        }

        previewObjectUrl = URL.createObjectURL(file);
        uploadPreviewImage.src = previewObjectUrl;
        uploadPreviewName.textContent = file.name;

        const probe = new Image();
        probe.onload = () => {
            uploadPreviewMeta.textContent = `${formatFileSize(file.size)} · ${probe.width} × ${probe.height}`;
        };
        probe.src = previewObjectUrl;

        uploadPreview.hidden = false;
        if (uploadEmptyNote) {
            uploadEmptyNote.hidden = true;
        }
    };

    const bindUploadPreview = () => {
        if (!uploadInput || !uploadDropzone) {
            return;
        }

        uploadInput.addEventListener("change", () => {
            const file = uploadInput.files?.[0];
            if (!file) {
                resetUploadPreview();
                return;
            }
            updateUploadPreview(file);
        });

        ["dragenter", "dragover"].forEach((eventName) => {
            uploadDropzone.addEventListener(eventName, (event) => {
                event.preventDefault();
                uploadDropzone.classList.add("is-dragover");
            });
        });

        ["dragleave", "drop"].forEach((eventName) => {
            uploadDropzone.addEventListener(eventName, (event) => {
                event.preventDefault();
                uploadDropzone.classList.remove("is-dragover");
            });
        });

        uploadDropzone.addEventListener("drop", (event) => {
            const files = event.dataTransfer?.files;
            if (!files || !files.length) {
                return;
            }

            uploadInput.files = files;
            updateUploadPreview(files[0]);
        });

        if (uploadModalElement) {
            uploadModalElement.addEventListener("hidden.bs.modal", () => {
                uploadForm?.reset();
                resetUploadPreview();
            });
        }
    };

    const updateDetailModal = (trigger) => {
        if (!detailModal || !trigger) {
            return;
        }

        const detailTitle = detailModal.querySelector("#detailImageTitle");
        const detailPreview = detailModal.querySelector("#detailImagePreview");
        const detailDescription = detailModal.querySelector("#detailImageDescription");
        const detailCreated = detailModal.querySelector("#detailImageCreated");
        const detailOrientation = detailModal.querySelector("#detailImageOrientation");
        const detailDimensions = detailModal.querySelector("#detailImageDimensions");
        const detailPeople = detailModal.querySelector("#detailImagePeople");
        const detailStorage = detailModal.querySelector("#detailImageStorage");
        const detailAnalysis = detailModal.querySelector("#detailImageAnalysis");
        const detailOpen = detailModal.querySelector("#detailImageOpen");
        const detailDownload = detailModal.querySelector("#detailImageDownload");
        const detailTags = detailModal.querySelector("#detailImageTags");

        if (detailTitle) {
            detailTitle.textContent = trigger.dataset.imageTitle || "Image";
        }
        if (detailPreview) {
            detailPreview.src = trigger.dataset.imageUrl || "";
            detailPreview.alt = trigger.dataset.imageTitle || "Image";
        }
        if (detailDescription) {
            detailDescription.textContent = trigger.dataset.imageDescription || "Aucune description disponible.";
        }
        if (detailCreated) {
            detailCreated.textContent = trigger.dataset.imageCreated || "-";
        }
        if (detailOrientation) {
            detailOrientation.textContent = trigger.dataset.imageOrientation || "-";
        }
        if (detailDimensions) {
            detailDimensions.textContent = trigger.dataset.imageDimensions || "-";
        }
        if (detailPeople) {
            detailPeople.textContent = trigger.dataset.imagePeople || "-";
        }
        if (detailStorage) {
            detailStorage.textContent = trigger.dataset.imageStorage || "-";
        }
        if (detailAnalysis) {
            detailAnalysis.textContent = trigger.dataset.imageAnalysis || "-";
        }
        if (detailOpen) {
            detailOpen.href = trigger.dataset.imageOpenUrl || "#";
        }
        if (detailDownload) {
            detailDownload.href = trigger.dataset.imageDownloadUrl || "#";
        }
        if (detailTags) {
            detailTags.innerHTML = "";
            let tags = [];

            try {
                tags = JSON.parse(trigger.dataset.imageTags || "[]");
            } catch (error) {
                tags = [];
            }

            tags.forEach((tag) => {
                const badge = document.createElement("span");
                badge.className = "tag-badge";
                badge.textContent = tag;
                detailTags.appendChild(badge);
            });
        }
    };

    const bindDetailModal = () => {
        if (!detailModal) {
            return;
        }

        detailModal.addEventListener("show.bs.modal", (event) => {
            updateDetailModal(event.relatedTarget);
        });
    };

    if (themeToggle) {
        themeToggle.addEventListener("click", () => {
            const nextTheme = doc.getAttribute("data-bs-theme") === "dark" ? "light" : "dark";
            window.localStorage.setItem("smartdam-theme", nextTheme);
            setTheme(nextTheme);
        });
    }

    initTheme();
    bindLoadingForms();
    bindUploadPreview();
    bindDetailModal();
})();
