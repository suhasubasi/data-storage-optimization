export default function Placeholder({ title, note }: { title: string; note: string }) {
  return (
    <section>
      <h2>{title}</h2>
      <p>{note}</p>
      <p className="todo">TODO Stream 1: build against src/mocks, then the real API.</p>
    </section>
  );
}
