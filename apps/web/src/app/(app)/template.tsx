/** Re-mounts on every navigation, so each page plays the entrance animation defined in globals.css (.page-enter). */
export default function AppTemplate({ children }: { children: React.ReactNode }) {
  return <div className="page-enter">{children}</div>;
}
