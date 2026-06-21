"use client";

/**
 * Table — thin table primitive for entity lists. Sticky header, zebra rows,
 * hover, mono cells via className.
 */
import type { ReactNode } from "react";
import { cx } from "../../lib/cx";

export interface TableProps<T> {
  columns: Array<{
    key: string;
    header: ReactNode;
    width?: string | number;
    align?: "left" | "right" | "center";
    mono?: boolean;
    className?: string;
    render: (row: T, index: number) => ReactNode;
  }>;
  rows: T[];
  rowKey: (row: T, index: number) => string;
  emptyState?: ReactNode;
  onRowClick?: (row: T) => void;
  density?: "comfortable" | "compact";
  className?: string;
}

export function Table<T>({
  columns,
  rows,
  rowKey,
  emptyState,
  onRowClick,
  density = "comfortable",
  className,
}: TableProps<T>) {
  return (
    <div className={cx("ax-table-wrap", className)} data-density={density}>
      <table className="ax-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                style={column.width ? { width: column.width } : undefined}
                data-align={column.align ?? "left"}
                className={column.mono ? "mono" : undefined}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && emptyState ? (
            <tr>
              <td colSpan={columns.length} className="ax-table__empty">
                {emptyState}
              </td>
            </tr>
          ) : (
            rows.map((row, index) => (
              <tr
                key={rowKey(row, index)}
                data-clickable={onRowClick ? "true" : undefined}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                className={cx(onRowClick && "ax-table__row--clickable")}
              >
                {columns.map((column) => (
                  <td
                    key={column.key}
                    data-align={column.align ?? "left"}
                    className={cx(column.mono && "mono", column.className)}
                  >
                    {column.render(row, index)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

/** Skeleton table — matches column count + 6 placeholder rows. */
export function TableSkeleton({
  columns,
  rows = 6,
}: {
  columns: number;
  rows?: number;
}) {
  return (
    <div className="ax-table-wrap" data-density="compact">
      <table className="ax-table">
        <thead>
          <tr>
            {Array.from({ length: columns }).map((_, i) => (
              <th key={i}>
                <span className="ax-skel ax-skel--text" style={{ width: "60%" }} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }).map((_, rowIndex) => (
            <tr key={rowIndex}>
              {Array.from({ length: columns }).map((_, colIndex) => (
                <td key={colIndex}>
                  <span
                    className="ax-skel ax-skel--text"
                    style={{ width: `${50 + ((rowIndex * columns + colIndex) % 5) * 10}%` }}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}