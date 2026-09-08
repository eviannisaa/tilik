import type { JSX } from "solid-js";
import { ErrorBoundary } from "solid-js";
import ReportSection from "./ReportSection";

/**
 * Keeps one broken section from taking the whole report with it.
 *
 * `api/services/report.py` already holds this line on the server: a provider
 * that fails costs its own section and nothing else. The panel did not hold it.
 * Any section that threw while rendering unmounted the entire report, and since
 * the skeleton is what shows until a report renders, the reader was left
 * watching a loading state that would never resolve. No error, no gaps notice,
 * no other section. Just the skeleton.
 *
 * That is not hypothetical. It happened the first time a field was added to the
 * report: a browser holding the new bundle asked an API still serving the old
 * shape, got a report with no `airQuality` in it, and the new section threw on
 * `undefined`. Every deploy has a window where those two disagree, and every
 * field added later reopens it.
 *
 * The fallback renders through {@link ReportSection}, not around it, so the
 * section keeps its anchor and its heading. The index above is built from a
 * separate list and scrolls to those anchors, so a broken section that rendered
 * nothing at all would leave a chip pointing at a section that does not exist.
 */
export default function SectionBoundary(props: {
     index: number;
     title: string;
     children: JSX.Element;
}) {
     return (
          <ErrorBoundary
               fallback={(error) => {
                    // The reader gets plain words; whoever is debugging gets the
                    // actual error, which is the only place it survives.
                    console.error(`Tilik: the ${props.title} section failed`, error);

                    return (
                         <ReportSection index={props.index} title={props.title}>
                              <p class="text-sm leading-relaxed text-ink-soft">
                                   This section could not be displayed. The rest
                                   of the report is unaffected, and nothing here
                                   should be read as a finding about this
                                   location.
                              </p>
                              <p class="mt-1 text-xs leading-relaxed text-ink-faint">
                                   Re-run the check to try again. If it keeps
                                   happening, reload the page: an open tab can
                                   be a version behind the service it is asking.
                              </p>
                         </ReportSection>
                    );
               }}
          >
               {props.children}
          </ErrorBoundary>
     );
}
