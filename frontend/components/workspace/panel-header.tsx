export function PanelHeader({
  number,
  title,
  subtitle,
}: {
  number: string;
  title: string;
  subtitle: string;
}) {
  return (
    <header className="panel-header">
      <span>{number}</span>
      <div>
        <h2>{title}</h2>
        <small>{subtitle}</small>
      </div>
    </header>
  );
}
