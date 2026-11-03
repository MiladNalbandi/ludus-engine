// The bulletin plugin's editor screen: module interface version 2.
//
// One ES module with no imports. The shell checks this file's bytes against the integrity the
// service recorded at install, then evaluates it, and calls the default export with `host`:
// React (the shell's own copy, so hooks work), the request helpers that send the signed-in
// author's token, and the shell's small UI pieces. A plugin that bundled its own React would
// break every hook it used.
export default function bulletin(host) {
  const { React, engine, ui } = host;
  const h = React.createElement;

  function Notice() {
    const [notice, setNotice] = React.useState(null);
    const [error, setError] = React.useState(null);

    React.useEffect(() => {
      let live = true;
      engine.sendJson('/api/v1/bulletin/notice').then(
        (body) => {
          if (live) setNotice(body);
        },
        (thrown) => {
          if (live) setError(thrown instanceof Error ? thrown.message : String(thrown));
        },
      );
      return () => {
        live = false;
      };
    }, []);

    return h(
      'main',
      { className: 'screen' },
      h(
        'header',
        { className: 'screen-header' },
        h(
          'div',
          null,
          h('h1', null, 'Bulletin'),
          h('p', { className: 'screen-lede' }, 'Notices for everyone who edits this project.'),
        ),
      ),
      h(ui.EngineError, { message: error }),
      notice
        ? h(
            'section',
            { className: 'panel bulletin-notice', 'aria-labelledby': 'bulletin-notice-title' },
            h('h2', { id: 'bulletin-notice-title' }, notice.title),
            h('p', null, notice.body),
            h(
              'ul',
              { className: 'bulletin-pins', 'aria-label': 'Pinned' },
              notice.pinned.map((pin) => h('li', { key: pin }, pin)),
            ),
          )
        : error
          ? null
          : h('p', { className: 'muted' }, 'Reading the notice…'),
    );
  }

  return {
    api: 2,
    app: 'bulletin',
    slug: 'bulletin',
    label: 'Bulletin',
    summary: 'Notices for the people editing',
    // Scoped by the shell to this module's screens. `.screen-lede` is the shell's own class: the
    // rule below changes it here and nowhere else.
    styles: `
      .screen-lede { font-style: italic; }
      .bulletin-notice { margin-top: 1.5rem; border-style: dashed; border-color: rgba(28, 169, 240, 0.55); }
      .bulletin-notice p { max-width: 38rem; }
      .bulletin-pins { list-style: none; margin: 1rem 0 0; padding: 0; }
      .bulletin-pins li { display: flex; align-items: center; gap: 0.6rem; padding: 0.3rem 0; color: var(--slate); }
      .bulletin-pins li::before { content: ''; width: 0.5rem; height: 0.5rem; border-radius: 50%; background: var(--blue); }
    `,
    routes: [{ path: '', title: 'Bulletin', screen: Notice }],
  };
}
