//! The shape of a tap's click: the samples a linear motor is driven with at
//! the strength slider's position.
//!
//! A click is not a buzz. Pushing the motor through a steady sine for the
//! whole length gives a finger hundreds of swings in a row, which it reads as
//! a rumble rather than as a tap; what it reads as a tap is a couple of swings
//! under an envelope that starts at once and dies away quickly. And what it
//! reads as a heavier click is how much of a swing it got, so the length
//! follows the slider along with the strength.

use std::time::Duration;

/// The rate a made click's samples are played at, the lowest the driver
/// takes: some fifty samples to each swing of the motor.
pub const RATE: u32 = 8000;

/// A made click: swings of the motor at its resonant frequency that drive it,
/// then swings turned over that stop it, so that it does not ring on.
const DRIVE_SWINGS: f32 = 2.0;
const BRAKE_SWINGS: f32 = 1.5;

/// How long a click runs at the lightest and at the heaviest the slider asks
/// for, in whole milliseconds. Twelve milliseconds of a swing at about two
/// hundred hertz is two or three swings and twenty-six is five or so, which is
/// what a linear motor's click is made of; held for much longer the same sine
/// stops being a click and becomes a buzz.
pub const LIGHT_CLICK_MS: u16 = 12;
pub const HEAVY_CLICK_MS: u16 = 26;

/// How long the click takes to come up, in whole milliseconds. A swing that
/// starts at its full strength cracks; one that starts over a millisecond is
/// the tick of a motor that is being told to stop.
pub const ATTACK_MS: u16 = 1;

/// How long a click of `length` takes to go away again: two fifths of it,
/// which is five milliseconds of the light click and ten of the heavy one.
pub fn fade_of(length: u16) -> u16 {
    u16::max(2, length * 2 / 5)
}

/// How long a click at the slider's `position` is, from the light click to the
/// heavy one.
pub fn length_of(position: f32) -> Duration {
    let at = position.clamp(0.0, 1.0);
    let light = f32::from(LIGHT_CLICK_MS);
    let heavy = f32::from(HEAVY_CLICK_MS);
    Duration::from_millis((light + (heavy - light) * at).round() as u64)
}

/// The share of the click's full strength at the slider's `position`.
///
/// The slider moves the strength in equal steps of the swing itself: every
/// tenth of the slider is the same tenth more of the throw. A factor per step,
/// which is what this used to be, is the same number of decibels between every
/// pair of neighbours, and a finger does not read a click's strength in
/// decibels: it reads how far the motor throws the glass.
pub fn share(lightest: f32, strongest: f32, position: f32) -> f32 {
    let at = position.clamp(0.0, 1.0);
    lightest + (strongest - lightest) * at
}

/// A click's samples at `rate` a second for a motor that swings at `hz`,
/// `length` long: swings that drive the motor and then swings turned over
/// that stop it, under an envelope that comes up over [`ATTACK_MS`] and dies
/// away over the last two fifths. How strong it plays is the effect's own
/// magnitude, not baked into the samples.
pub fn made(hz: f32, length: Duration, rate: u32) -> Vec<i8> {
    let millis = length.as_millis() as u16;
    let all = (length.as_secs_f32() * rate as f32).round() as usize;
    let drive = (all as f32 * DRIVE_SWINGS / (DRIVE_SWINGS + BRAKE_SWINGS)).round() as usize;
    let attack = (f32::from(ATTACK_MS) / 1000.0 * rate as f32).round().max(1.0);
    let fade = (f32::from(fade_of(millis)) / 1000.0 * rate as f32).round().max(1.0);
    (0..all)
        .map(|i| {
            let wave = (std::f32::consts::TAU * hz * i as f32 / rate as f32).sin() * f32::from(i8::MAX);
            let k = envelope(i, all, attack, fade);
            ((if i < drive { wave } else { -wave }) * k).round() as i8
        })
        .collect()
}

/// How much of the full throw a click's sample at `i` of `all` is given: from
/// nothing up to the full over `attack` samples, then down to nothing over
/// `fade` of them at the end.
fn envelope(i: usize, all: usize, attack: f32, fade: f32) -> f32 {
    let up = (i as f32 / attack).min(1.0);
    let down = ((all - i) as f32 / fade).min(1.0);
    up.min(down)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_click_runs_longer_the_further_the_slider_is_pushed() {
        let light = u128::from(LIGHT_CLICK_MS);
        let heavy = u128::from(HEAVY_CLICK_MS);
        assert_eq!((length_of(0.0).as_millis(), length_of(1.0).as_millis()), (light, heavy));
        assert_eq!((length_of(-1.0).as_millis(), length_of(2.0).as_millis()), (light, heavy), "no further than its ends");
        let mut last = 0;
        for step in 0..=10 {
            let length = length_of(step as f32 / 10.0).as_millis();
            assert!(length >= last, "the click never gets shorter as the slider goes up: {length} after {last}");
            last = length;
        }
        assert!(heavy > light, "there is a click between the ends of the slider to tell apart");
    }

    #[test]
    fn a_click_comes_up_at_once_and_dies_away_before_its_samples_run_out() {
        let length = length_of(0.5);
        let all = (length.as_secs_f32() * RATE as f32).round() as usize;
        let attack = (f32::from(ATTACK_MS) / 1000.0 * RATE as f32).round();
        let fade = (f32::from(fade_of(length.as_millis() as u16)) / 1000.0 * RATE as f32).round();
        assert_eq!((attack as usize, fade as usize), (8, 56), "a millisecond up and seven down of the nineteen");
        assert_eq!(envelope(0, all, attack, fade), 0.0, "it starts from nothing");
        assert_eq!(envelope(attack as usize, all, attack, fade), 1.0, "and is full a millisecond in");
        assert!(envelope(all - 1, all, attack, fade) < 0.05, "and all but gone when the samples run out");
        assert!(all >= attack as usize + fade as usize, "the envelope fits in the click");
    }

    #[test]
    fn a_made_click_drives_whole_swings_then_turns_over() {
        let length = length_of(0.5);
        let samples = made(172.4, length, RATE);
        let all = (length.as_secs_f32() * RATE as f32).round() as usize;
        let drive = (all as f32 * DRIVE_SWINGS / (DRIVE_SWINGS + BRAKE_SWINGS)).round() as usize;
        assert_eq!(samples.len(), all, "as long as the slider asks: {length:?}");
        assert_eq!(samples[0], 0);
        assert_eq!(*samples[..drive].iter().max().unwrap(), i8::MAX, "the drive swings to the full");
        assert!(*samples[drive..].iter().min().unwrap() <= -100, "turned over, it swings the other way");
    }

    #[test]
    fn the_slider_moves_the_strength_in_equal_steps() {
        let (lightest, strongest) = (0.25, 1.0);
        assert_eq!((share(lightest, strongest, 0.0), share(lightest, strongest, 1.0)), (lightest, strongest));
        assert!((share(lightest, strongest, 0.5) - 0.625).abs() < 1e-6, "halfway is halfway in between");
        for step in 0..10 {
            let here = share(lightest, strongest, step as f32 / 10.0);
            let next = share(lightest, strongest, (step + 1) as f32 / 10.0);
            assert!((next - here - 0.075).abs() < 1e-6, "every tenth of the slider is the same step: {here} to {next}");
        }
        assert_eq!((share(lightest, strongest, -1.0), share(lightest, strongest, 2.0)), (lightest, strongest), "no further than its ends");
    }
}
