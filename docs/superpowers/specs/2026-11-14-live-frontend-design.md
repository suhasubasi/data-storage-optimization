# Promote the selected frontend design

The user selected the existing `frontend-prototype` design and requested it become the real frontend. Promote its UI into `frontend/`, retaining the existing React 18, Vite 5, TypeScript, and shared contracts. The normal app remains on port 5173 and uses real FastAPI data on port 8000.

## Approach

Copy the prototype's presentation, pages, components, and supporting hooks into the canonical frontend. Keep the canonical API client and router configuration: the API interfaces match. This avoids maintaining two active frontends or rebuilding a design the user already selected. Keep `frontend-prototype/` as a reference.

## Scope and constraints

All nine screens, navigation, search, media inspection, uploads, processing, downloads, storage, offboarding and settings remain available. Preserve the design and responsive CSS. Update standalone-prototype branding to the active workspace, retaining accurate simulated-source and unofficial-product disclosures. Configure both development and build preview to proxy the backend.

No backend, contract, database or original-media changes. No new dependencies. Save the old frontend source/configuration before replacement because this workspace has no Git repository. Public hosting is outside this local frontend promotion.

User clarification: desktop use only. Desktop is the acceptance target; no additional mobile work is requested.

## Verification

Run TypeScript checking and production build. Browse every route with the real backend, inspect desktop/mobile layout and interactive search/filter/navigation. Check build preview's API proxy and error handling. Review the migration against its backup and reference prototype.
