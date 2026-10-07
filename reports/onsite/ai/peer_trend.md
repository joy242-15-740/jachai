# Peer and trend (validation check)

Peer and trend does not add a fourth blocking score. The payment, shop and network scores still decide the queue. This view says where a shop sits among shops of the same category, area and size, and whether its recent payment scores are climbing before they cross the payment threshold.

Early warning: rising flag (slope > 0 and day-7 forecast at least 0.02 above today's mean payment score) while today's mean score is still under the payment threshold. Entered review: some later validation day, within 7 days and not past validation_end, has a payment score at or above that threshold. Misuse-shop counts use the hidden shop label only as context.

Seed 42, profile `fast`. Payment threshold 0.667. Validation shop-days with a later validation day: 212. Rising: 16. Early warning (rising and still under the threshold): 16. Of those, entered review within the observed horizon: 1 (share 0.062). Early-warning shop-days sitting on a misuse shop: 3.

The fast validation window is only a few days long, and the 7-day horizon is cut at validation_end so the test period stays unread. A low hit rate can mean the flag is early, or that it is noise. Both readings stay open at this sample size.

The case page reads `GET /shops/{shop_id}/peer-trend`. The panel is a cue. An analyst decides.
