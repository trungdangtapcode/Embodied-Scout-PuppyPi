import { useEffect, useState } from "preact/hooks";
import { api } from "./api";
import { t } from "./i18n";

type Component = {
  name: string;
  implementation: string;
  description: string;
  source: string;
  research_repository: string | null;
  configured_model?: string;
  configured_revision?: string;
  enabled?: boolean;
};
type Inventory = { mode: string; configured_encoder: string; components: Component[] };

export function ImplementationInfo() {
  const [inventory, setInventory] = useState<Inventory | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let disposed = false;
    void api<Inventory>("/implementation").then(
      (value) => {
        if (!disposed) setInventory(value);
      },
      (reason) => {
        if (!disposed) setError(String(reason));
      },
    );
    return () => {
      disposed = true;
    };
  }, []);
  return (
    <aside class="method-disclosure" aria-label={t("Implementation disclosure")}>
      <strong>{t("Methods and evidence")}</strong>
      {!inventory && <p>{error || t("Loading implementation inventory…")}</p>}
      {inventory && (
        <>
          <p>
            {t(
              inventory.configured_encoder === "spatial_appearance"
                ? "Object matching: handcoded Python/OpenCV baseline. Mind Palace model inference is a separate optional workflow."
                : "Object matching uses the configured encoder; configuration alone does not prove model execution.",
            )}
          </p>
          <details>
            <summary>{t("Inspect implementations and sources")}</summary>
            <p>
              {t(
                "This is a code/configuration inventory. Per-run model evidence is in job traces; a listed dependency is not proof of inference or research quality.",
              )}
            </p>
            <div class="method-inventory">
              {inventory.components.map((c) => (
                <section key={c.name}>
                  <h3>{t(c.name)}</h3>
                  <code>{c.implementation}</code>
                  <p>{t(c.description)}</p>
                  <small>{c.source}</small>
                  {c.configured_model && (
                    <small>
                      {t("Configured model")}: {c.configured_model} ·{" "}
                      {t(c.enabled ? "Enabled" : "Disabled")}
                    </small>
                  )}
                  {c.configured_revision && (
                    <small>
                      {t("Configured revision")}: {c.configured_revision}
                    </small>
                  )}
                  {c.research_repository && (
                    <a href={c.research_repository} target="_blank" rel="noreferrer">
                      {t("Upstream source")}
                    </a>
                  )}
                </section>
              ))}
            </div>
          </details>
        </>
      )}
    </aside>
  );
}
