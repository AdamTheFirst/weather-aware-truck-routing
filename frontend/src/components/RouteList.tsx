import { LEVEL_COLORS, LEVEL_LABELS, LEVEL_ORDER, ROUTE_COLORS, formatDuration } from '../format';
import type { Plan } from '../types';

interface Props {
  plan: Plan;
  selectedId: string;
  onSelect: (id: string) => void;
}

/** One card per route, with a stacked bar showing how many miles fall in each risk level. */
export default function RouteList({ plan, selectedId, onSelect }: Props) {
  return (
    <div className="route-list">
      <p className="reason">{plan.recommendation_reason}</p>
      {plan.routes.map((r) => {
        const m = r.summary.miles_by_level;
        const recommended = r.id === plan.recommended_id;
        return (
          <button
            key={r.id}
            className={`route-card ${r.id === selectedId ? 'selected' : ''}`}
            onClick={() => onSelect(r.id)}
            style={{ borderLeftColor: ROUTE_COLORS[r.id] }}
          >
            <div className="route-head">
              <strong>Route {r.id}</strong>
              {recommended && <span className="badge">Recommended</span>}
            </div>
            {r.via && <div className="via">via {r.via}</div>}
            <div className="stats">
              <span>{Math.round(r.distance_mi)} mi</span>
              <span>{formatDuration(r.duration_s)}</span>
              <span>avg risk {r.summary.avg_risk.toFixed(2)}</span>
            </div>
            <div className="risk-bar" aria-label="Miles by risk level">
              {LEVEL_ORDER.map((lvl) =>
                m[lvl] > 0 ? (
                  <span
                    key={lvl}
                    style={{ flexGrow: m[lvl], background: LEVEL_COLORS[lvl] }}
                    title={`${LEVEL_LABELS[lvl]}: ${m[lvl]} mi`}
                  />
                ) : null,
              )}
            </div>
            <div className="risk-miles">
              {(['severe', 'high', 'no_travel'] as const).map((lvl) =>
                m[lvl] > 0 ? (
                  <span key={lvl} style={{ color: LEVEL_COLORS[lvl] }}>
                    {m[lvl]} mi {LEVEL_LABELS[lvl]}
                  </span>
                ) : null,
              )}
              {m.severe === 0 && m.high === 0 && m.no_travel === 0 && <span className="muted">No high-risk miles</span>}
            </div>
          </button>
        );
      })}
    </div>
  );
}
