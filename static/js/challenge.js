document.addEventListener('DOMContentLoaded', function () {
    let stars = document.querySelectorAll('.rating .fa-star');
    let ratingInput = document.getElementById('rating');
    let userRating = ratingInput.value;

    if (userRating) {
        for (let i = 0; i < userRating; i++) {
            stars[i].classList.remove('far');
            stars[i].classList.add('fas', 'filled');
        }
    }

    stars.forEach(star => {
        star.addEventListener('click', function () {
            let rating = this.getAttribute('data-rating');
            ratingInput.value = rating;

            stars.forEach((s, index) => {
                if (index < rating) {
                    s.classList.remove('far');
                    s.classList.add('fas', 'filled');
                } else {
                    s.classList.remove('fas', 'filled');
                    s.classList.add('far');
                }
            });
        });

        star.addEventListener('mouseover', function () {
            let rating = this.getAttribute('data-rating');

            stars.forEach((s, index) => {
                if (index < rating) {
                    s.classList.add('hover');
                } else {
                    s.classList.remove('hover');
                }
            });
        });

        star.addEventListener('mouseout', function () {
            stars.forEach(star => {
                star.classList.remove('hover');
            });
        });
    });
});
