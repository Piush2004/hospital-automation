import ChatWidget from "./ChatWidget.jsx";

export default function App() {
  return (
    <div className="page">
      <header className="page-header">
        <h1>Hospital Automation</h1>
        <p>Local demo chat — triage, doctor assignment, and booking, end to end.</p>
      </header>
      <ChatWidget />
    </div>
  );
}
