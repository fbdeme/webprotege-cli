# WebProtégé control surface (2019 monolithic image) — reverse-engineering notes

This documents *how* a self-hosted WebProtégé instance can be driven programmatically,
and *why* this CLI uses headless-browser automation instead of speaking the wire protocol
directly. Findings are from decompiling the shipped JARs of
`protegeproject/webprotege:latest` (`4.0.0-beta-3`, the only published tag) with
[CFR](https://github.com/leibnitz27/cfr) and probing a running instance.

> TL;DR: the 2019 image exposes **no REST API**. Every feature goes through a single
> GWT-RPC servlet, authentication is a CHAP handshake over that servlet, and the request/
> response payloads lean on dozens of custom GWT serializers. Hand-rolling a wire client is
> possible but is a large, brittle surface; driving the app's own JavaScript in a headless
> browser is the robust, maintainable choice.

## 1. There is no REST

`WEB-INF/web.xml` declares **no servlet mappings** — only a single catch-all filter
(`WebProtegeWebAppFilter` on `url-pattern: *`) that routes everything internally. So the
endpoint map lives in code, not config.

Probing the running instance:

| Path | Method | Result | Meaning |
|---|---|---|---|
| `/` | GET | 200 | host page (`WebProtege.jsp`) loads the GWT module `webprotege/webprotege.nocache.js` |
| `/webprotege/dispatchservice` | POST | 500 (empty body) | **the GWT-RPC endpoint** — exists |
| `/download` | GET | 403 (no session) / 400 (bad params) | project export, but **requires an authenticated session** |
| `/dispatch`, `/fileupload`, `/webprotege/dispatch` | any | 404 | red herrings |

The GWT module base URL is `/webprotege/` (from the host page's `<script src>`), and the
dispatch service's relative path is declared on the interface:

```java
@RemoteServiceRelativePath("dispatchservice")
public interface DispatchService extends RemoteService {
    DispatchServiceResultContainer executeAction(Action var1) throws ...;
}
```

→ full endpoint = `/webprotege/dispatchservice`. **Every** server action handler is reachable
only through this one method `executeAction(Action)`:
`GetAvailableProjectsAction`, `CreateClassesAction`, `CreateDataPropertiesAction`,
`AddAxiomsAction`, `DeleteEntitiesAction`, `GetRevisionsAction`,
`Get/SetOntologyAnnotationsAction`, `MoveProjectsToTrashAction`, … — all there, all GWT-RPC.

There is exactly **one** non-GWT endpoint, `/download`, and it still needs the session cookie
the GWT login flow sets. So there is **no unauthenticated surface at all**.

## 2. Authentication is CHAP (not a form POST)

Login is a two-step Challenge-Handshake over the dispatch servlet, not a `username/password`
form. Relevant classes: `GetChapSessionActionHandler`, `PerformLoginActionHandler`,
`ChapSessionManager`, `ChapResponseChecker`, `ChapResponseDigestAlgorithm`,
`PasswordDigestAlgorithm`, `Md5MessageDigestAlgorithm`.

The exact math (all digests are **MD5**), reconstructed from the decompiled classes:

```
# server returns, per (user, session): a random Salt and a random ChallengeMessage
saltedPasswordDigest = MD5( utf8( base16_lower(salt_bytes) ) || utf8( clear_text_password ) )
chapResponse         = MD5( challenge_bytes || saltedPasswordDigest_bytes )
```

- `PasswordDigestAlgorithm.getDigestOfSaltedPassword(pwd, salt)`: lowercase-hex the salt,
  UTF-8 encode that hex string, append the UTF-8 password bytes, MD5.
- `ChapResponseDigestAlgorithm.getChapResponseDigest(challenge, saltedPwd)`: MD5 of raw
  challenge bytes followed by the raw 16-byte salted-password digest.

Flow: `GetChapSessionAction(userId)` → `{ chapSessionId, challenge, salt }`; compute the
response above; `PerformLoginAction(chapSessionId, userId, chapResponse)` → sets the session
cookie. (The browser's GWT client does all of this in obfuscated JS; the server-side
`ChapResponseChecker` recomputes and compares.)

## 3. The custom-serializer wall

The GWT-RPC payloads are not plain JSON. Each transmitted type is serialized positionally
against a per-build *serialization policy* (the `*.gwt.rpc` strong-name files shipped under
`/webprotege/`), and **many** types ship their own `CustomFieldSerializer` (mostly AutoValue):
`AvailableProject`, `ProjectDetails`, `NewProjectSettings`, `LoadProjectResult`, the entity
data types (`OWLClassData`, `OWLObjectPropertyData`, …), the frame types (`ClassFrame`,
`NamedIndividualFrame`, …), `EntityGraph`, `Tag`, and more.

Consequence: a from-scratch wire client must (a) implement the GWT-RPC stream
reader/writer, (b) replicate CHAP, **and** (c) re-implement each custom serializer for every
action it wants to call. Login (`GetChapSession`/`PerformLogin`) is tractable, but real
operations (list/create projects, edit frames) immediately hit the serializer wall.

## 4. Why this CLI uses a headless browser

| Approach | Auth | Serialization | Writes (create/edit) | Robustness vs. effort |
|---|---|---|---|---|
| Hand-rolled GWT-RPC | re-implement CHAP | re-implement every custom serializer | each action = new serializer | brittle, large, ongoing |
| **Headless browser (this CLI)** | the app's JS does it | the app's JS does it | drive the real UI the app already ships | robust; cost is selectors |

We **pin the image** anyway (see the `webprotege-selfhost` runbook — `mongo:4.0`, fixed
WebProtégé tag), so the usual knock against UI automation (a moving DOM) is largely neutralized:
the UI is frozen with the image. Browser automation lets the app's own JavaScript handle CHAP
and every custom serializer, so we get correct create/list/export/edit for free and only
maintain a thin layer of selectors.

### Possible future fast-path
For read-only, serializer-light actions it may be worth adding a raw-HTTP fast-path: log in
once via the browser, reuse the `JSESSIONID` cookie, and hit `/download` (plain GET) for
exports — skipping a browser launch when only an export is needed. The write path stays on the
browser.

## Reproducing these findings
```bash
# pull a JAR out of the running container and decompile a class
docker cp webprotege:/usr/local/tomcat/webapps/ROOT/WEB-INF/lib/<jar> ./x.jar
unzip -o x.jar 'edu/stanford/bmir/protege/web/**' -d ext
java -jar cfr.jar ext/<path>/<Class>.class      # CFR 0.152

# confirm the serialization policy whitelists an action
docker exec webprotege sh -c 'grep -l <SomeAction> /usr/local/tomcat/webapps/ROOT/webprotege/*.gwt.rpc'
```
