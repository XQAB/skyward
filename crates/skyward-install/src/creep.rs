//! How far the install bar creeps while `update_engine` says nothing.
//!
//! It lives here, outside the module that only builds for the phone, so the
//! arithmetic is tested by the workspace's own `cargo test` on the computer
//! instead of only being compiled for Android and linted.

use std::time::Duration;

/// The share of the write the creep stops at, so a real number from
/// `update_engine` can still take the bar over.
const SHORT_OF: f32 = 0.9;

/// How long the creep takes to come within about a third of that share.
const TIME_CONSTANT: f32 = 60.0;

/// How far the bar creeps while the engine says nothing: the share of the
/// write grows with a time constant of a minute, and stays a tenth of all
/// of it short so a real number can still move it.
pub fn creeping(total: u64, elapsed: Duration) -> u64 {
    let share = 1.0 - (-(elapsed.as_secs_f32() / TIME_CONSTANT)).exp();
    let share = share.clamp(0.0, SHORT_OF);
    let creeped = (total as f64 * f64::from(share)) as u64;
    creeped.min(short_of(total))
}

/// The most of the write the creep reaches, the same share it stays short
/// of all of it by, worked out in whole bytes.
fn short_of(total: u64) -> u64 {
    total / 10 * 9
}

#[cfg(test)]
mod tests {
    use super::creeping;
    use std::time::Duration;

    /// A gigabyte, big enough that a byte here or there does not matter.
    const ALL: u64 = 1 << 30;
    const SHORT: u64 = ALL / 10 * 9;

    #[test]
    fn nothing_is_crept_before_any_time_goes_by() {
        assert_eq!(creeping(ALL, Duration::ZERO), 0);
    }

    #[test]
    fn a_minute_in_the_bar_is_past_half() {
        assert!(creeping(ALL, Duration::from_secs(60)) > ALL / 2);
    }

    #[test]
    fn it_stops_short_of_all_of_it_and_comes_close() {
        let waited = creeping(ALL, Duration::from_secs(600));
        assert!(waited <= SHORT, "{waited} went past {SHORT}");
        assert!(SHORT - waited <= ALL / 1000, "{} short of {SHORT}", SHORT - waited);
    }

    #[test]
    fn however_long_it_runs_it_never_passes_what_it_stops_short_of() {
        let later = creeping(ALL, Duration::from_secs(3600));
        assert!(later <= SHORT, "{later} went past {SHORT}");
    }
}
