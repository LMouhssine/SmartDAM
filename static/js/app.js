(() => {
    const loadingOverlay = document.getElementById("loadingOverlay");
    const loadingMessage = document.getElementById("loadingMessage");
    const uploadInput = document.getElementById("uploadModalInput");
    const uploadEmptyNote = document.getElementById("uploadEmptyNote");
    const uploadDropzone = document.getElementById("uploadDropzone");
    const uploadForm = document.getElementById("uploadForm");
    const uploadModalElement = document.getElementById("uploadModal");
    const uploadSubmitButton = document.getElementById("uploadSubmitButton");
    const uploadFileList = document.getElementById("uploadFileList");
    const uploadCounter = document.getElementById("uploadCounter");
    const uploadCounterText = document.getElementById("uploadCounterText");
    const uploadSubmitLabel = document.getElementById("uploadSubmitLabel");
    const detailModalElement = document.getElementById("imageDetailModal");
    const deleteModalElement = document.getElementById("deleteImageModal");

    const detailModal = detailModalElement ? bootstrap.Modal.getOrCreateInstance(detailModalElement) : null;
    const deleteModal = deleteModalElement ? bootstrap.Modal.getOrCreateInstance(deleteModalElement) : null;

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

    const renderTagsAsLinks = (container, tagsJson) => {
        container.innerHTML = "";
        let tags = [];
        try {
            tags = JSON.parse(tagsJson || "[]");
        } catch (_error) {
            tags = [];
        }
        tags.forEach((tag) => {
            const link = document.createElement("a");
            link.className = "tag-badge tag-badge--link";
            link.textContent = tag;
            link.href = `/search?q=${encodeURIComponent(tag)}`;
            container.appendChild(link);
        });
    };

    const bindFavoriteToggles = () => {
        document.querySelectorAll("[data-favorite-toggle]").forEach((button) => {
            button.addEventListener("click", async () => {
                const url = button.dataset.favoriteUrl;
                if (!url) return;
                try {
                    const response = await fetch(url, { method: "POST" });
                    if (!response.ok) throw new Error("Request failed");
                    const data = await response.json();
                    const isFav = data.is_favorite;
                    button.textContent = isFav ? "\u2605" : "\u2606";
                    button.classList.toggle("is-favorite", isFav);
                    button.setAttribute("aria-label", isFav ? "Retirer des favoris" : "Ajouter aux favoris");
                    button.setAttribute("title", isFav ? "Retirer des favoris" : "Ajouter aux favoris");
                } catch (_err) {
                    // Silent failure — state stays as-is
                }
            });
        });
    };

    const bindDetailFavoriteButton = () => {
        const btn = detailModalElement?.querySelector("#detailImageFavorite");
        const label = detailModalElement?.querySelector("#detailFavoriteLabel");
        if (!btn) return;

        btn.addEventListener("click", async () => {
            const url = btn.dataset.favoriteUrl;
            const imageId = btn.dataset.imageId;
            if (!url) return;

            try {
                const response = await fetch(url, { method: "POST" });
                if (!response.ok) throw new Error("Request failed");
                const data = await response.json();
                const isFav = data.is_favorite;

                if (label) label.textContent = isFav ? "Retirer des favoris" : "Ajouter aux favoris";
                btn.classList.toggle("is-active-fav", isFav);

                // Sync the card's star button on the page
                if (imageId) {
                    const cardStar = document.querySelector(`[data-favorite-toggle][data-image-id="${imageId}"]`);
                    if (cardStar) {
                        cardStar.textContent = isFav ? "\u2605" : "\u2606";
                        cardStar.classList.toggle("is-favorite", isFav);
                        cardStar.setAttribute("aria-label", isFav ? "Retirer des favoris" : "Ajouter aux favoris");
                        cardStar.setAttribute("title", isFav ? "Retirer des favoris" : "Ajouter aux favoris");
                    }
                    // Also update the Voir button's data attr for next modal open
                    const voirBtn = document.querySelector(`[data-image-id="${imageId}"][data-bs-toggle="modal"]`);
                    if (voirBtn) voirBtn.dataset.imageFavorite = isFav ? "true" : "false";
                }
            } catch (_err) {
                // Silent failure
            }
        });
    };

    const bindDetailReanalyzeButton = () => {
        const btn = detailModalElement?.querySelector("#detailImageReanalyze");
        const label = detailModalElement?.querySelector("#detailReanalyzeLabel");
        const spinner = detailModalElement?.querySelector("#detailImageReanalyze .spinner-border");
        const status = detailModalElement?.querySelector("#detailReanalyzeStatus");
        if (!btn) return;

        btn.addEventListener("click", async () => {
            const url = btn.dataset.reanalyzeUrl;
            const imageId = btn.dataset.imageId;
            if (!url) return;

            btn.disabled = true;
            if (label) label.textContent = "Analyse en cours...";
            spinner?.classList.remove("d-none");
            if (status) status.classList.add("d-none");

            try {
                const response = await fetch(url, { method: "POST" });
                const data = await response.json();
                if (!response.ok) throw new Error(data.error || "Erreur inconnue");

                // Update description
                const desc = detailModalElement.querySelector("#detailImageDescription");
                if (desc) desc.textContent = data.description || "Aucune description disponible.";

                // Update analysis label
                const analysis = detailModalElement.querySelector("#detailImageAnalysis");
                if (analysis) analysis.textContent = data.analysis_label || "-";

                // Rebuild tags as clickable links
                const tagsContainer = detailModalElement.querySelector("#detailImageTags");
                if (tagsContainer) renderTagsAsLinks(tagsContainer, JSON.stringify(data.tags || []));

                // Update Voir button data attrs so modal reopens with fresh data
                if (imageId) {
                    const voirBtn = document.querySelector(`[data-image-id="${imageId}"][data-bs-toggle="modal"]`);
                    if (voirBtn) {
                        voirBtn.dataset.imageDescription = data.description || "";
                        voirBtn.dataset.imageAnalysis = data.analysis_label || "";
                        voirBtn.dataset.imageTags = JSON.stringify(data.tags || []);
                    }
                }

                if (status) {
                    status.textContent = "Analyse mise à jour.";
                    status.className = "detail-reanalyze-status text-success";
                    status.classList.remove("d-none");
                    setTimeout(() => status.classList.add("d-none"), 3000);
                }
            } catch (err) {
                if (status) {
                    status.textContent = err.message || "L'analyse a échoué.";
                    status.className = "detail-reanalyze-status text-danger";
                    status.classList.remove("d-none");
                }
            } finally {
                btn.disabled = false;
                if (label) label.textContent = "Ré-analyser";
                spinner?.classList.add("d-none");
            }
        });
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

    const escapeHtml = (str) => {
        const d = document.createElement("div");
        d.textContent = str;
        return d.innerHTML;
    };

    const formatFileSize = (bytes) => {
        if (!bytes) return "0 Ko";
        if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
        return `${Math.max(1, Math.round(bytes / 1024))} Ko`;
    };

    const bindUploadPanel = () => {
        if (!uploadInput || !uploadDropzone || !uploadForm) return;

        let pendingFiles = [];

        const renderFileList = () => {
            if (!uploadFileList) return;

            if (!pendingFiles.length) {
                uploadFileList.hidden = true;
                if (uploadEmptyNote) uploadEmptyNote.hidden = false;
                if (uploadSubmitButton) uploadSubmitButton.disabled = true;
                if (uploadSubmitLabel) uploadSubmitLabel.textContent = "Envoyer les images";
                return;
            }

            uploadFileList.hidden = false;
            if (uploadEmptyNote) uploadEmptyNote.hidden = true;
            if (uploadSubmitButton) uploadSubmitButton.disabled = false;

            const count = pendingFiles.length;
            if (uploadSubmitLabel) {
                uploadSubmitLabel.textContent = count === 1 ? "Envoyer 1 image" : `Envoyer ${count} images`;
            }

            uploadFileList.innerHTML = "";
            pendingFiles.forEach((file, idx) => {
                const item = document.createElement("div");
                item.className = "upload-file-item upload-file-item--pending";
                item.id = `upload-item-${idx}`;
                item.innerHTML = `
                    <div>
                        <div class="upload-file-item__name">${escapeHtml(file.name)}</div>
                        <div class="upload-file-item__size">${formatFileSize(file.size)}</div>
                    </div>
                    <div class="upload-file-item__status">En attente…</div>
                `;
                uploadFileList.appendChild(item);
            });
        };

        const setItemState = (idx, state, message) => {
            const item = document.getElementById(`upload-item-${idx}`);
            if (!item) return;
            item.className = `upload-file-item upload-file-item--${state}`;
            const statusEl = item.querySelector(".upload-file-item__status");
            if (!statusEl) return;
            if (state === "uploading") {
                statusEl.innerHTML = `<span class="upload-step-spinner"></span> ${escapeHtml(message)}`;
            } else {
                statusEl.textContent = message;
            }
        };

        uploadInput.addEventListener("change", () => {
            pendingFiles = Array.from(uploadInput.files || []);
            renderFileList();
        });

        ["dragenter", "dragover"].forEach((ev) => {
            uploadDropzone.addEventListener(ev, (e) => {
                e.preventDefault();
                uploadDropzone.classList.add("is-dragover");
            });
        });

        ["dragleave", "drop"].forEach((ev) => {
            uploadDropzone.addEventListener(ev, (e) => {
                e.preventDefault();
                uploadDropzone.classList.remove("is-dragover");
            });
        });

        uploadDropzone.addEventListener("drop", (e) => {
            const files = e.dataTransfer?.files;
            if (!files || !files.length) return;
            const merged = new DataTransfer();
            Array.from(uploadInput.files || []).forEach((f) => merged.items.add(f));
            Array.from(files).forEach((f) => merged.items.add(f));
            uploadInput.files = merged.files;
            pendingFiles = Array.from(merged.files);
            renderFileList();
        });

        uploadModalElement?.addEventListener("hidden.bs.modal", () => {
            pendingFiles = [];
            uploadInput.value = "";
            if (uploadFileList) { uploadFileList.hidden = true; uploadFileList.innerHTML = ""; }
            if (uploadEmptyNote) uploadEmptyNote.hidden = false;
            if (uploadCounter) uploadCounter.hidden = true;
            if (uploadSubmitButton) {
                uploadSubmitButton.disabled = true;
                uploadSubmitButton.querySelector(".spinner-border")?.classList.add("d-none");
            }
            if (uploadSubmitLabel) uploadSubmitLabel.textContent = "Envoyer les images";
        });

        uploadForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            if (!pendingFiles.length) return;

            if (uploadSubmitButton) {
                uploadSubmitButton.disabled = true;
                uploadSubmitButton.querySelector(".spinner-border")?.classList.remove("d-none");
            }

            let doneCount = 0;
            let errorCount = 0;
            const total = pendingFiles.length;

            const updateCounter = () => {
                if (!uploadCounter || !uploadCounterText) return;
                uploadCounter.hidden = false;
                uploadCounterText.textContent = `${doneCount + errorCount} / ${total} traitée${total > 1 ? "s" : ""}`;
            };

            for (let i = 0; i < pendingFiles.length; i++) {
                const file = pendingFiles[i];
                setItemState(i, "uploading", "Analyse IA en cours…");

                const formData = new FormData();
                formData.append("image", file, file.name);

                try {
                    const response = await fetch("/upload/async", { method: "POST", body: formData });
                    const data = await response.json();

                    if (!response.ok || data.status === "error") {
                        throw new Error(data.message || `HTTP ${response.status}`);
                    }

                    const tagCount = data.tags?.length ?? 0;
                    const sourceLabel = data.analysis_label || data.analysis_source || "Analysé";
                    setItemState(i, "done", `✓ ${tagCount} tag${tagCount !== 1 ? "s" : ""} · ${sourceLabel}`);
                    doneCount++;
                } catch (err) {
                    setItemState(i, "error", `✗ ${err.message || "Échec de l'envoi"}`);
                    errorCount++;
                }

                updateCounter();
            }

            if (uploadSubmitButton) {
                uploadSubmitButton.disabled = false;
                uploadSubmitButton.querySelector(".spinner-border")?.classList.add("d-none");
            }

            if (doneCount > 0) {
                setTimeout(() => window.location.reload(), 900);
            }
        });
    };

    const populateDeleteModal = ({ deleteUrl, imageTitle }) => {
        if (!deleteModalElement || !deleteUrl) {
            return;
        }

        const deleteForm = deleteModalElement.querySelector("#deleteImageForm");
        const deleteName = deleteModalElement.querySelector("#deleteImageName");
        const deleteNextInput = deleteModalElement.querySelector("#deleteNextInput");

        if (deleteForm) {
            deleteForm.action = deleteUrl;
        }
        if (deleteName) {
            deleteName.textContent = imageTitle || "image";
        }
        if (deleteNextInput) {
            deleteNextInput.value = `${window.location.pathname}${window.location.search}`;
        }
    };

    const openDeleteModal = ({ deleteUrl, imageTitle }) => {
        if (!deleteModal) {
            return;
        }

        populateDeleteModal({ deleteUrl, imageTitle });
        deleteModal.show();
    };

    const updateDetailModal = (trigger) => {
        if (!detailModalElement || !trigger) {
            return;
        }

        const detailTitle = detailModalElement.querySelector("#detailImageTitle");
        const detailPreview = detailModalElement.querySelector("#detailImagePreview");
        const detailDescription = detailModalElement.querySelector("#detailImageDescription");
        const detailCreated = detailModalElement.querySelector("#detailImageCreated");
        const detailOrientation = detailModalElement.querySelector("#detailImageOrientation");
        const detailDimensions = detailModalElement.querySelector("#detailImageDimensions");
        const detailPeople = detailModalElement.querySelector("#detailImagePeople");
        const detailStorage = detailModalElement.querySelector("#detailImageStorage");
        const detailAnalysis = detailModalElement.querySelector("#detailImageAnalysis");
        const detailOpen = detailModalElement.querySelector("#detailImageOpen");
        const detailDownload = detailModalElement.querySelector("#detailImageDownload");
        const detailTags = detailModalElement.querySelector("#detailImageTags");
        const detailDelete = detailModalElement.querySelector("#detailImageDelete");

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
            detailOpen.href = trigger.dataset.imageUrl || "#";
        }
        if (detailDownload) {
            detailDownload.href = trigger.dataset.imageDownloadUrl || "#";
        }
        if (detailDelete) {
            detailDelete.dataset.deleteUrl = trigger.dataset.imageDeleteUrl || "";
            detailDelete.dataset.imageTitle = trigger.dataset.imageTitle || "image";
        }
        if (detailTags) {
            renderTagsAsLinks(detailTags, trigger.dataset.imageTags);
        }

        const detailFavorite = detailModalElement.querySelector("#detailImageFavorite");
        const detailFavoriteLabel = detailModalElement.querySelector("#detailFavoriteLabel");
        if (detailFavorite && detailFavoriteLabel) {
            const isFav = trigger.dataset.imageFavorite === "true";
            detailFavoriteLabel.textContent = isFav ? "Retirer des favoris" : "Ajouter aux favoris";
            detailFavorite.dataset.favoriteUrl = trigger.dataset.imageFavoriteUrl || "";
            detailFavorite.dataset.imageId = trigger.dataset.imageId || "";
            detailFavorite.classList.toggle("is-active-fav", isFav);
        }

        const detailReanalyze = detailModalElement.querySelector("#detailImageReanalyze");
        if (detailReanalyze) {
            detailReanalyze.dataset.reanalyzeUrl = trigger.dataset.imageReanalyzeUrl || "";
            detailReanalyze.dataset.imageId = trigger.dataset.imageId || "";
        }
    };

    const bindDetailModal = () => {
        if (!detailModalElement) {
            return;
        }

        detailModalElement.addEventListener("show.bs.modal", (event) => {
            updateDetailModal(event.relatedTarget);
        });

        const detailDelete = detailModalElement.querySelector("#detailImageDelete");
        if (detailDelete) {
            detailDelete.addEventListener("click", () => {
                if (!detailDelete.dataset.deleteUrl) {
                    return;
                }

                const payload = {
                    deleteUrl: detailDelete.dataset.deleteUrl,
                    imageTitle: detailDelete.dataset.imageTitle,
                };

                const handleHidden = () => {
                    detailModalElement.removeEventListener("hidden.bs.modal", handleHidden);
                    openDeleteModal(payload);
                };

                detailModalElement.addEventListener("hidden.bs.modal", handleHidden);
                detailModal?.hide();
            });
        }
    };

    const bindDeleteTriggers = () => {
        document.querySelectorAll("[data-delete-trigger]").forEach((button) => {
            button.addEventListener("click", () => {
                openDeleteModal({
                    deleteUrl: button.dataset.deleteUrl,
                    imageTitle: button.dataset.imageTitle,
                });
            });
        });
    };

    const bindDynamicSearch = () => {
        const globalSearch = document.getElementById("global-search");
        const filterForm = document.querySelector(".filter-form");

        if (globalSearch) {
            let searchTimer = null;
            globalSearch.addEventListener("input", () => {
                clearTimeout(searchTimer);
                searchTimer = setTimeout(() => {
                    globalSearch.closest("form")?.requestSubmit();
                }, 400);
            });
        }

        if (!filterForm) return;

        ["filter-people", "filter-food", "filter-environment", "filter-orientation", "filter-sort"].forEach((id) => {
            document.getElementById(id)?.addEventListener("change", () => filterForm.requestSubmit());
        });
        document.getElementById("filter-favorites")?.addEventListener("change", () => filterForm.requestSubmit());
    };

    bindLoadingForms();
    bindUploadPanel();
    bindDetailModal();
    bindDeleteTriggers();
    bindFavoriteToggles();
    bindDetailFavoriteButton();
    bindDetailReanalyzeButton();
    bindDynamicSearch();
})();
