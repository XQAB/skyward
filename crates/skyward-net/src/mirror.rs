//! Which mirror this network reaches fastest: a slice of the file each one
//! hands out is timed, and the quickest is the one the download goes
//! through, so a network that GitHub caps or a mirror that is down costs no
//! more than the timing itself.

use anyhow::{bail, Context, Result};
use std::io::Read;
use std::time::{Duration, Instant};

/// How much of a file each mirror hands over while it is timed: enough for
/// the rate to read true, and little enough that timing five mirrors costs
/// a few seconds on a network that works at all.
pub const SAMPLE: u64 = 256 * 1024;

/// How long one read may go without a byte before a mirror is given up on:
/// one that stalls is left out, not counted as the slowest.
pub const STALL: Duration = Duration::from_secs(6);

/// How fast `url` handed over a slice of the file it holds, in bytes a
/// second, or why it did not.
///
/// A mirror that refuses the range, or sends nothing, gives no rate: it is
/// no answer rather than a slow one, and the download's own list of
/// addresses keeps it as the last resort either way.
pub fn rate(agent: &ureq::Agent, url: &str, sample: u64, stall: Duration) -> Result<u64> {
    let started = Instant::now();
    let mut response = agent
        .get(url)
        .header("Range", format!("bytes=0-{}", sample.saturating_sub(1)))
        .config()
        .timeout_per_read(Some(stall))
        .build()
        .call()
        .with_context(|| format!("reach {url}"))?;
    // A server that ignores the range sends the file whole, and what comes
    // first is timed the same.
    match response.status().as_u16() {
        200 | 206 => {}
        status => bail!("the server answered {status}"),
    }
    let mut body = response.body_mut().with_config().limit(sample).reader();
    let mut buf = vec![0u8; 64 * 1024];
    let mut got = 0u64;
    while got < sample {
        let n = body.read(&mut buf).with_context(|| format!("read what {url} sent"))?;
        if n == 0 {
            break;
        }
        got += n as u64;
    }
    if got == 0 {
        bail!("{url} sent nothing");
    }
    let took = started.elapsed().as_secs_f64();
    // A clock that cannot tell the difference between nothing and everything
    // would make the rate infinite; a nanosecond is the least it can mean.
    Ok((got as f64 / took.max(1e-9)) as u64)
}

/// Which of the rates read is the one to take: the quickest, and none when
/// a rate of zero stands for a mirror that gave no answer and no mirror is
/// left to choose.
///
/// The first place is no mirror at all, the file straight from GitHub, so
/// GitHub winning the timing leaves the pages as they were.
pub fn quickest(rates: &[u64]) -> Option<usize> {
    let mut quickest: Option<usize> = None;
    for (at, rate) in rates.iter().enumerate() {
        if *rate == 0 {
            continue;
        }
        if quickest.is_none_or(|q| *rate > rates[q]) {
            quickest = Some(at);
        }
    }
    quickest
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A server on this computer that answers one request with `answer`.
    fn server(answer: Vec<u8>) -> (String, std::thread::JoinHandle<()>) {
        use std::io::{Read, Write};
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let url = format!("http://{}/f", listener.local_addr().unwrap());
        let held = std::thread::spawn(move || {
            let (mut s, _) = listener.accept().unwrap();
            let mut request = Vec::new();
            let mut chunk = [0u8; 512];
            while !request.ends_with(b"\r\n\r\n") {
                let n = s.read(&mut chunk).unwrap();
                request.extend_from_slice(&chunk[..n]);
            }
            s.write_all(&answer).unwrap();
        });
        (url, held)
    }

    fn body(status: &str, bytes: &[u8]) -> Vec<u8> {
        let mut answer = format!("HTTP/1.1 {status}\r\nContent-Length: {}\r\n\r\n", bytes.len()).into_bytes();
        answer.extend_from_slice(bytes);
        answer
    }

    #[test]
    fn the_quickest_of_them_is_the_one_taken() {
        assert_eq!(quickest(&[0, 3, 9, 5]), Some(2));
        assert_eq!(quickest(&[0, 0]), None, "none answered");
        assert_eq!(quickest(&[]), None, "nothing was timed");
    }

    #[test]
    fn a_tie_goes_to_whichever_came_first() {
        assert_eq!(quickest(&[7, 7]), Some(0));
        assert_eq!(quickest(&[0, 7, 7]), Some(1));
    }

    #[test]
    fn no_mirror_is_a_rate_like_any_other() {
        assert_eq!(quickest(&[9, 0, 0]), Some(0), "straight from GitHub when that is quickest");
        assert_eq!(quickest(&[0, 9, 0]), Some(1), "through the mirror that is");
    }

    #[test]
    fn a_slice_that_came_has_a_rate_and_a_refusal_has_none() {
        let agent = crate::http::agent(Default::default());
        let (url, held) = server(body("206 Partial Content", &[7u8; 4096]));
        let read = rate(&agent, &url, 4096, Duration::from_secs(2)).unwrap();
        assert!(read > 0, "the slice came, so it has a rate: {read}");
        held.join().unwrap();
        let (url, held) = server(body("404 Not Found", &[]));
        assert!(rate(&agent, &url, 4096, Duration::from_secs(2)).is_err(), "a refusal is no rate");
        held.join().unwrap();
        let (url, held) = server(body("206 Partial Content", &[]));
        assert!(rate(&agent, &url, 4096, Duration::from_secs(2)).is_err(), "nothing came, so there is nothing to time");
        held.join().unwrap();
    }
}
