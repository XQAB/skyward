//! How far the install bar has got, and how it keeps moving while
//! `update_engine` says nothing.
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

/// Where the bar goes: whatever has been counted so far, but never behind
/// how long this write has been going.
///
/// `update_engine` can say how far it has got and then go quiet for
/// minutes, which is where the bar used to freeze; with this the creep is
/// a floor throughout, so it keeps moving through that silence as well.
/// The creep stops a tenth of all of it short, so a number the engine does
/// say — which is usually the further one by then — always wins.
pub fn along(total: u64, elapsed: Duration, counted: u64) -> u64 {
    counted.min(total).max(creeping(total, elapsed))
}

/// How far the bar creeps by time alone: the share of the write grows with
/// a time constant of a minute, and stays a tenth of all of it short.
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
    use super::{along, creeping};
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

    #[test]
    fn a_number_the_engine_says_is_where_the_bar_is() {
        let said = ALL / 100 * 40;
        assert_eq!(along(ALL, Duration::ZERO, said), said);
        assert_eq!(along(ALL, Duration::from_secs(1), said), said);
    }

    #[test]
    fn the_bar_keeps_moving_when_the_engine_goes_quiet_after_a_number() {
        // 40% and then silence for ten minutes: the bar must not stay at 40%.
        let said = ALL / 100 * 40;
        let later = along(ALL, Duration::from_secs(600), said);
        assert!(later > said, "{later} stayed at {said}");
        assert!(later <= SHORT, "{later} went past {SHORT}");
    }

    #[test]
    fn a_number_past_the_creep_is_kept_whole() {
        // 95% is further than the creep ever goes, so it is not cut back.
        let said = ALL / 100 * 95;
        assert_eq!(along(ALL, Duration::from_secs(600), said), said);
    }

    #[test]
    fn more_counted_than_the_package_is_never_shown_as_more() {
        assert_eq!(along(ALL, Duration::ZERO, ALL + 4096), ALL);
    }
}
